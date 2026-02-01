"""Trading execution engine for Polymarket."""

import asyncio
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum
import structlog

from .client import PolymarketClient, Order, Position, Market

logger = structlog.get_logger()


class TradeAction(Enum):
    """Possible trading actions."""

    BUY_YES = "buy_yes"
    BUY_NO = "buy_no"
    SELL_YES = "sell_yes"
    SELL_NO = "sell_no"
    HOLD = "hold"


@dataclass
class TradeSignal:
    """Signal from the prediction engine."""

    market_id: str
    action: TradeAction
    confidence: float  # 0-1
    predicted_probability: float  # 0-1, for YES outcome
    current_price: float
    expected_edge: float  # predicted_probability - current_price
    size_recommendation: float
    reasoning: str


@dataclass
class TradeResult:
    """Result of a trade execution."""

    success: bool
    order_id: Optional[str] = None
    market_id: str = ""
    action: TradeAction = TradeAction.HOLD
    size: float = 0.0
    price: float = 0.0
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class RiskLimits:
    """Risk management limits."""

    max_position_size: float = 100.0
    max_daily_loss: float = 500.0
    max_single_trade: float = 50.0
    max_positions: int = 10
    min_edge: float = 0.05
    min_confidence: float = 0.65


class TradingExecutor:
    """Executes trades with risk management."""

    def __init__(
        self,
        client: PolymarketClient,
        risk_limits: Optional[RiskLimits] = None,
        dry_run: bool = True,
    ):
        self.client = client
        self.risk_limits = risk_limits or RiskLimits()
        self.dry_run = dry_run

        # Track daily P&L
        self._daily_pnl: float = 0.0
        self._daily_reset: datetime = datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        self._trade_history: list[TradeResult] = []
        self._positions: dict[str, Position] = {}

    async def execute_signal(self, signal: TradeSignal) -> TradeResult:
        """Execute a trade based on a signal."""
        # Reset daily P&L if new day
        self._check_daily_reset()

        # Validate signal
        validation_error = self._validate_signal(signal)
        if validation_error:
            logger.warning(
                "Signal validation failed",
                market_id=signal.market_id,
                error=validation_error,
            )
            return TradeResult(
                success=False,
                market_id=signal.market_id,
                action=signal.action,
                error=validation_error,
            )

        # Check risk limits
        risk_error = await self._check_risk_limits(signal)
        if risk_error:
            logger.warning(
                "Risk limit exceeded",
                market_id=signal.market_id,
                error=risk_error,
            )
            return TradeResult(
                success=False,
                market_id=signal.market_id,
                action=signal.action,
                error=risk_error,
            )

        # Calculate position size
        size = self._calculate_position_size(signal)

        # Build order
        order = self._build_order(signal, size)

        if self.dry_run:
            logger.info(
                "DRY RUN - Would execute trade",
                market_id=signal.market_id,
                action=signal.action.value,
                size=size,
                price=signal.current_price,
            )
            return TradeResult(
                success=True,
                order_id="dry_run",
                market_id=signal.market_id,
                action=signal.action,
                size=size,
                price=signal.current_price,
            )

        # Execute trade
        try:
            result = await self.client.place_order(order)

            trade_result = TradeResult(
                success=True,
                order_id=result.get("id"),
                market_id=signal.market_id,
                action=signal.action,
                size=size,
                price=signal.current_price,
            )

            self._trade_history.append(trade_result)

            logger.info(
                "Trade executed successfully",
                order_id=result.get("id"),
                market_id=signal.market_id,
                action=signal.action.value,
                size=size,
            )

            return trade_result

        except Exception as e:
            logger.error(
                "Trade execution failed",
                market_id=signal.market_id,
                error=str(e),
            )
            return TradeResult(
                success=False,
                market_id=signal.market_id,
                action=signal.action,
                error=str(e),
            )

    async def execute_batch(
        self,
        signals: list[TradeSignal],
        max_concurrent: int = 3,
    ) -> list[TradeResult]:
        """Execute multiple signals with rate limiting."""
        results = []

        # Sort by confidence/edge
        sorted_signals = sorted(
            signals,
            key=lambda s: s.confidence * abs(s.expected_edge),
            reverse=True,
        )

        # Execute in batches
        for i in range(0, len(sorted_signals), max_concurrent):
            batch = sorted_signals[i:i + max_concurrent]
            batch_results = await asyncio.gather(
                *[self.execute_signal(s) for s in batch],
                return_exceptions=True,
            )

            for j, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    results.append(TradeResult(
                        success=False,
                        market_id=batch[j].market_id,
                        action=batch[j].action,
                        error=str(result),
                    ))
                else:
                    results.append(result)

            # Rate limit between batches
            if i + max_concurrent < len(sorted_signals):
                await asyncio.sleep(1)

        return results

    async def close_position(self, market_id: str) -> TradeResult:
        """Close an existing position."""
        if market_id not in self._positions:
            return TradeResult(
                success=False,
                market_id=market_id,
                error="No position found",
            )

        position = self._positions[market_id]

        # Create opposing trade
        action = TradeAction.SELL_YES if position.outcome == 0 else TradeAction.SELL_NO

        signal = TradeSignal(
            market_id=market_id,
            action=action,
            confidence=1.0,
            predicted_probability=0.5,
            current_price=position.current_price,
            expected_edge=0.0,
            size_recommendation=position.size,
            reasoning="Position close",
        )

        return await self.execute_signal(signal)

    async def close_all_positions(self) -> list[TradeResult]:
        """Close all open positions."""
        await self._refresh_positions()

        results = []
        for market_id in list(self._positions.keys()):
            result = await self.close_position(market_id)
            results.append(result)

        return results

    async def _refresh_positions(self):
        """Refresh positions from the API."""
        try:
            positions = await self.client.get_positions()
            self._positions = {p.market_id: p for p in positions}
        except Exception as e:
            logger.error("Failed to refresh positions", error=str(e))

    def _validate_signal(self, signal: TradeSignal) -> Optional[str]:
        """Validate a trading signal."""
        if signal.action == TradeAction.HOLD:
            return "HOLD action - no trade needed"

        if signal.confidence < self.risk_limits.min_confidence:
            return f"Confidence {signal.confidence:.2f} below minimum {self.risk_limits.min_confidence}"

        if abs(signal.expected_edge) < self.risk_limits.min_edge:
            return f"Edge {signal.expected_edge:.2f} below minimum {self.risk_limits.min_edge}"

        if signal.current_price <= 0 or signal.current_price >= 1:
            return f"Invalid price {signal.current_price}"

        return None

    async def _check_risk_limits(self, signal: TradeSignal) -> Optional[str]:
        """Check if trade would exceed risk limits."""
        # Check daily loss
        if self._daily_pnl < -self.risk_limits.max_daily_loss:
            return f"Daily loss limit exceeded: {self._daily_pnl:.2f}"

        # Check position count
        await self._refresh_positions()
        if len(self._positions) >= self.risk_limits.max_positions:
            if signal.market_id not in self._positions:
                return f"Max positions ({self.risk_limits.max_positions}) reached"

        # Check existing position size
        if signal.market_id in self._positions:
            existing = self._positions[signal.market_id]
            if existing.size >= self.risk_limits.max_position_size:
                return f"Max position size reached for {signal.market_id}"

        return None

    def _calculate_position_size(self, signal: TradeSignal) -> float:
        """Calculate optimal position size using Kelly criterion."""
        # Simplified Kelly: f = (bp - q) / b
        # where b = odds, p = probability of win, q = 1 - p

        edge = abs(signal.expected_edge)
        confidence = signal.confidence

        # Base size on edge and confidence
        kelly_fraction = edge * confidence

        # Apply half-Kelly for safety
        kelly_fraction *= 0.5

        # Calculate dollar size
        base_size = self.risk_limits.max_single_trade
        size = base_size * kelly_fraction

        # Apply limits
        size = min(size, self.risk_limits.max_single_trade)
        size = min(size, signal.size_recommendation)
        size = max(size, 1.0)  # Minimum $1

        return round(size, 2)

    def _build_order(self, signal: TradeSignal, size: float) -> Order:
        """Build an order from a signal."""
        if signal.action == TradeAction.BUY_YES:
            side = "BUY"
            outcome = 0
            price = signal.current_price
        elif signal.action == TradeAction.BUY_NO:
            side = "BUY"
            outcome = 1
            price = 1 - signal.current_price
        elif signal.action == TradeAction.SELL_YES:
            side = "SELL"
            outcome = 0
            price = signal.current_price
        else:  # SELL_NO
            side = "SELL"
            outcome = 1
            price = 1 - signal.current_price

        return Order(
            market_id=signal.market_id,
            side=side,
            outcome=outcome,
            size=size,
            price=price,
        )

    def _check_daily_reset(self):
        """Reset daily P&L at midnight."""
        now = datetime.utcnow()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        if today > self._daily_reset:
            self._daily_pnl = 0.0
            self._daily_reset = today
            logger.info("Daily P&L reset")

    def get_trade_history(
        self,
        since: Optional[datetime] = None,
    ) -> list[TradeResult]:
        """Get trade history."""
        if since:
            return [t for t in self._trade_history if t.timestamp >= since]
        return self._trade_history.copy()

    def get_daily_stats(self) -> dict:
        """Get daily trading statistics."""
        self._check_daily_reset()

        today_trades = [
            t for t in self._trade_history
            if t.timestamp >= self._daily_reset
        ]

        successful = [t for t in today_trades if t.success]

        return {
            "daily_pnl": self._daily_pnl,
            "total_trades": len(today_trades),
            "successful_trades": len(successful),
            "open_positions": len(self._positions),
            "daily_loss_limit": self.risk_limits.max_daily_loss,
            "loss_limit_remaining": self.risk_limits.max_daily_loss + self._daily_pnl,
        }
