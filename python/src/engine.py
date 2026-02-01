"""Main prediction and trading engine."""

import asyncio
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass, field
import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .config import settings
from .polymarket.client import PolymarketClient, Market
from .polymarket.markets import MarketFetcher
from .signals.base import MarketContext
from .polymarket.trading import TradingExecutor, TradeResult, RiskLimits
from .signals.ensemble import EnsemblePredictor, EnsemblePrediction

logger = structlog.get_logger()


@dataclass
class EngineState:
    """Current state of the trading engine."""

    running: bool = False
    last_cycle: Optional[datetime] = None
    cycles_completed: int = 0
    total_trades: int = 0
    successful_trades: int = 0
    total_pnl: float = 0.0
    active_markets: int = 0
    last_predictions: list[EnsemblePrediction] = field(default_factory=list)
    last_trades: list[TradeResult] = field(default_factory=list)


class TradingEngine:
    """Main trading engine that orchestrates predictions and execution."""

    def __init__(
        self,
        dry_run: bool = True,
        trade_interval_minutes: int = 15,
    ):
        self.dry_run = dry_run
        self.trade_interval = trade_interval_minutes

        # Initialize components
        self.client = PolymarketClient(
            api_key=settings.polymarket.api_key,
            api_secret=settings.polymarket.api_secret,
            private_key=settings.polymarket.private_key,
        )

        self.market_fetcher = MarketFetcher(self.client)

        self.predictor = EnsemblePredictor(
            weights={
                "technical": settings.signal_weights.technical,
                "sentiment": settings.signal_weights.sentiment,
                "market_data": settings.signal_weights.market_data,
                "volatility": settings.signal_weights.volatility,
            },
            news_api_key=settings.external_apis.news_api_key,
            coingecko_api_key=settings.external_apis.coingecko_api_key,
        )

        risk_limits = RiskLimits(
            max_position_size=settings.trading.max_position_size,
            max_daily_loss=settings.trading.max_daily_loss,
            min_edge=settings.thresholds.min_edge,
            min_confidence=settings.thresholds.min_confidence,
        )

        self.executor = TradingExecutor(
            client=self.client,
            risk_limits=risk_limits,
            dry_run=dry_run,
        )

        self.state = EngineState()
        self._scheduler: Optional[AsyncIOScheduler] = None
        self._shutdown_event = asyncio.Event()

    async def start(self):
        """Start the trading engine."""
        if self.state.running:
            logger.warning("Engine already running")
            return

        logger.info(
            "Starting trading engine",
            dry_run=self.dry_run,
            interval_minutes=self.trade_interval,
        )

        # Validate settings
        errors = settings.validate()
        if errors:
            for error in errors:
                logger.error("Configuration error", error=error)
            if not self.dry_run:
                raise ValueError("Invalid configuration for live trading")

        # Initialize components
        await self.predictor.initialize()

        # Start scheduler
        self._scheduler = AsyncIOScheduler()
        self._scheduler.add_job(
            self._run_cycle,
            trigger=IntervalTrigger(minutes=self.trade_interval),
            id="trading_cycle",
            name="Trading Cycle",
            next_run_time=datetime.utcnow(),  # Run immediately
        )
        self._scheduler.start()

        self.state.running = True
        logger.info("Trading engine started")

    async def stop(self):
        """Stop the trading engine."""
        if not self.state.running:
            return

        logger.info("Stopping trading engine")

        if self._scheduler:
            self._scheduler.shutdown(wait=False)

        await self.predictor.shutdown()

        self.state.running = False
        self._shutdown_event.set()

        logger.info("Trading engine stopped")

    async def run_forever(self):
        """Run the engine until stopped."""
        await self.start()
        await self._shutdown_event.wait()

    async def _run_cycle(self):
        """Run a single trading cycle."""
        cycle_start = datetime.utcnow()
        logger.info("Starting trading cycle", cycle=self.state.cycles_completed + 1)

        try:
            # Step 1: Fetch tradeable markets
            markets = await self.market_fetcher.get_tradeable_markets(
                min_volume=1000,
                min_liquidity=500,
            )

            self.state.active_markets = len(markets)

            if not markets:
                logger.warning("No tradeable markets found")
                return

            logger.info("Found tradeable markets", count=len(markets))

            # Step 2: Build market contexts
            contexts = await self._build_contexts(markets)

            # Step 3: Generate predictions
            predictions = await self.predictor.predict_batch(contexts)

            self.state.last_predictions = predictions

            # Filter to actionable predictions
            actionable = [
                p for p in predictions
                if p.recommended_action.value != "hold"
                and abs(p.expected_edge) >= settings.thresholds.min_edge
                and p.combined_confidence >= settings.thresholds.min_confidence
            ]

            logger.info(
                "Generated predictions",
                total=len(predictions),
                actionable=len(actionable),
            )

            if not actionable:
                logger.info("No actionable predictions this cycle")
                return

            # Step 4: Execute trades
            trade_signals = [
                p.to_trade_signal(size_recommendation=50.0)
                for p in actionable
            ]

            results = await self.executor.execute_batch(trade_signals)

            self.state.last_trades = results
            self.state.total_trades += len(results)
            self.state.successful_trades += sum(1 for r in results if r.success)

            # Log results
            for result in results:
                if result.success:
                    logger.info(
                        "Trade executed",
                        market_id=result.market_id,
                        action=result.action.value,
                        size=result.size,
                    )
                else:
                    logger.warning(
                        "Trade failed",
                        market_id=result.market_id,
                        error=result.error,
                    )

        except Exception as e:
            logger.error("Cycle failed", error=str(e))

        finally:
            self.state.last_cycle = cycle_start
            self.state.cycles_completed += 1

            cycle_duration = (datetime.utcnow() - cycle_start).total_seconds()
            logger.info(
                "Trading cycle complete",
                cycle=self.state.cycles_completed,
                duration_seconds=cycle_duration,
            )

    async def _build_contexts(
        self,
        markets: list[Market],
    ) -> list[MarketContext]:
        """Build market contexts with historical data."""
        contexts = []

        for market in markets:
            try:
                # Get historical data if available
                price_history = []
                volume_history = []
                timestamps = []

                # Try to get price history
                if market.outcome_prices:
                    # Use token ID from market if available
                    try:
                        history = await self.market_fetcher.get_market_history(
                            market.id,
                            market.id,  # Simplified - would need actual token ID
                            hours=24,
                        )
                        if history:
                            price_history = history.prices
                            volume_history = history.volumes
                            timestamps = history.timestamps
                    except Exception:
                        pass

                context = MarketContext(
                    market_id=market.id,
                    question=market.question,
                    description=market.description,
                    current_price=market.outcome_prices[0] if market.outcome_prices else 0.5,
                    volume_24h=market.volume,
                    liquidity=market.liquidity,
                    end_date=market.end_date,
                    price_history=price_history or [market.outcome_prices[0]] * 20 if market.outcome_prices else [0.5] * 20,
                    volume_history=volume_history,
                    timestamps=timestamps,
                    category=market.category,
                )

                contexts.append(context)

            except Exception as e:
                logger.warning(
                    "Failed to build context",
                    market_id=market.id,
                    error=str(e),
                )

        return contexts

    async def run_single_cycle(self) -> dict:
        """Run a single cycle manually and return results."""
        if not self.state.running:
            await self.predictor.initialize()

        await self._run_cycle()

        return {
            "cycle": self.state.cycles_completed,
            "markets_analyzed": self.state.active_markets,
            "predictions": len(self.state.last_predictions),
            "trades_executed": len(self.state.last_trades),
            "successful_trades": sum(1 for t in self.state.last_trades if t.success),
        }

    def get_state(self) -> dict:
        """Get current engine state."""
        return {
            "running": self.state.running,
            "dry_run": self.dry_run,
            "last_cycle": self.state.last_cycle.isoformat() if self.state.last_cycle else None,
            "cycles_completed": self.state.cycles_completed,
            "total_trades": self.state.total_trades,
            "successful_trades": self.state.successful_trades,
            "active_markets": self.state.active_markets,
            "trade_interval_minutes": self.trade_interval,
        }

    def get_predictions(self) -> list[dict]:
        """Get last predictions."""
        return [
            {
                "market_id": p.market_id,
                "direction": p.direction.value,
                "confidence": p.combined_confidence,
                "predicted_probability": p.predicted_probability,
                "current_price": p.current_price,
                "expected_edge": p.expected_edge,
                "recommended_action": p.recommended_action.value,
                "timestamp": p.timestamp.isoformat(),
            }
            for p in self.state.last_predictions
        ]

    def get_trades(self) -> list[dict]:
        """Get last trades."""
        return [
            {
                "success": t.success,
                "order_id": t.order_id,
                "market_id": t.market_id,
                "action": t.action.value,
                "size": t.size,
                "price": t.price,
                "error": t.error,
                "timestamp": t.timestamp.isoformat(),
            }
            for t in self.state.last_trades
        ]


# Factory function for creating engine
def create_engine(
    dry_run: bool = True,
    trade_interval_minutes: int = 15,
) -> TradingEngine:
    """Create a configured trading engine."""
    return TradingEngine(
        dry_run=dry_run,
        trade_interval_minutes=trade_interval_minutes,
    )
