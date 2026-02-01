"""Market data fetching and management."""

import asyncio
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass, field
import structlog

from .client import PolymarketClient, Market

logger = structlog.get_logger()


@dataclass
class MarketSnapshot:
    """Point-in-time snapshot of market data."""

    market: Market
    timestamp: datetime
    bid_price: float
    ask_price: float
    spread: float
    volume_24h: float
    price_change_24h: float


@dataclass
class MarketHistory:
    """Historical data for a market."""

    market_id: str
    prices: list[float] = field(default_factory=list)
    timestamps: list[datetime] = field(default_factory=list)
    volumes: list[float] = field(default_factory=list)


class MarketFetcher:
    """Fetches and manages market data."""

    def __init__(self, client: PolymarketClient):
        self.client = client
        self._market_cache: dict[str, Market] = {}
        self._history_cache: dict[str, MarketHistory] = {}
        self._snapshot_cache: dict[str, MarketSnapshot] = {}
        self._last_fetch: Optional[datetime] = None

    async def fetch_crypto_markets(self, force_refresh: bool = False) -> list[Market]:
        """Fetch all crypto-related markets."""
        # Use cache if recent
        if not force_refresh and self._last_fetch:
            if datetime.utcnow() - self._last_fetch < timedelta(minutes=5):
                return list(self._market_cache.values())

        markets = await self.client.get_crypto_markets(limit=200)

        # Update cache
        self._market_cache = {m.id: m for m in markets}
        self._last_fetch = datetime.utcnow()

        logger.info("Fetched crypto markets", count=len(markets))
        return markets

    async def get_market_snapshot(self, market_id: str) -> Optional[MarketSnapshot]:
        """Get current snapshot of a market."""
        try:
            market = await self.client.get_market(market_id)

            # Get orderbook for bid/ask
            bid_price = market.outcome_prices[0] if market.outcome_prices else 0.5
            ask_price = market.outcome_prices[1] if len(market.outcome_prices) > 1 else 0.5

            # Try to get more accurate bid/ask from orderbook
            try:
                if hasattr(market, 'tokens') and market.tokens:
                    orderbook = await self.client.get_orderbook(market.tokens[0])
                    if orderbook.get("bids"):
                        bid_price = float(orderbook["bids"][0]["price"])
                    if orderbook.get("asks"):
                        ask_price = float(orderbook["asks"][0]["price"])
            except Exception:
                pass

            spread = abs(ask_price - bid_price)

            snapshot = MarketSnapshot(
                market=market,
                timestamp=datetime.utcnow(),
                bid_price=bid_price,
                ask_price=ask_price,
                spread=spread,
                volume_24h=market.volume,
                price_change_24h=0.0,  # Would need historical data
            )

            self._snapshot_cache[market_id] = snapshot
            return snapshot

        except Exception as e:
            logger.error("Failed to get market snapshot", market_id=market_id, error=str(e))
            return None

    async def get_market_history(
        self,
        market_id: str,
        token_id: str,
        hours: int = 24,
    ) -> Optional[MarketHistory]:
        """Get historical price data for a market."""
        try:
            history_data = await self.client.get_price_history(
                token_id=token_id,
                interval=f"{hours}h",
                fidelity=60,  # 1-minute intervals
            )

            history = MarketHistory(market_id=market_id)

            for point in history_data:
                history.timestamps.append(
                    datetime.fromtimestamp(point["t"])
                )
                history.prices.append(float(point["p"]))
                if "v" in point:
                    history.volumes.append(float(point["v"]))

            self._history_cache[market_id] = history
            return history

        except Exception as e:
            logger.error("Failed to get market history", market_id=market_id, error=str(e))
            return None

    async def get_tradeable_markets(
        self,
        min_volume: float = 1000,
        min_liquidity: float = 500,
        max_spread: float = 0.10,
    ) -> list[Market]:
        """Get markets that meet trading criteria."""
        markets = await self.fetch_crypto_markets()

        tradeable = []
        for market in markets:
            # Skip closed or inactive markets
            if market.closed or not market.active:
                continue

            # Check volume
            if market.volume < min_volume:
                continue

            # Check liquidity
            if market.liquidity < min_liquidity:
                continue

            # Check spread (approximate)
            if len(market.outcome_prices) >= 2:
                spread = abs(market.outcome_prices[0] - market.outcome_prices[1])
                if spread > max_spread:
                    continue

            tradeable.append(market)

        logger.info(
            "Found tradeable markets",
            total=len(markets),
            tradeable=len(tradeable),
        )

        return tradeable

    async def rank_markets_by_opportunity(
        self,
        markets: list[Market],
    ) -> list[tuple[Market, float]]:
        """Rank markets by trading opportunity score."""
        scored_markets = []

        for market in markets:
            score = self._calculate_opportunity_score(market)
            scored_markets.append((market, score))

        # Sort by score descending
        scored_markets.sort(key=lambda x: x[1], reverse=True)

        return scored_markets

    def _calculate_opportunity_score(self, market: Market) -> float:
        """Calculate opportunity score for a market."""
        score = 0.0

        # Volume score (log scale)
        if market.volume > 0:
            import math
            score += min(math.log10(market.volume) / 6, 1.0) * 30

        # Liquidity score
        if market.liquidity > 0:
            import math
            score += min(math.log10(market.liquidity) / 5, 1.0) * 20

        # Price near 0.5 means more uncertainty = more opportunity
        if market.outcome_prices:
            price = market.outcome_prices[0]
            uncertainty = 1 - abs(price - 0.5) * 2
            score += uncertainty * 30

        # Time until end (prefer markets with some time left)
        if market.end_date:
            days_left = (market.end_date - datetime.utcnow()).days
            if days_left > 0:
                time_score = min(days_left / 30, 1.0) * 20
                score += time_score

        return score
