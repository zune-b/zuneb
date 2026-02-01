"""Market data signal generator using external crypto price data."""

from typing import Optional
from datetime import datetime, timedelta
import httpx
import structlog

from .base import SignalGenerator, Signal, SignalDirection, MarketContext

logger = structlog.get_logger()


# Mapping from market assets to CoinGecko IDs
ASSET_TO_COINGECKO = {
    "bitcoin": "bitcoin",
    "ethereum": "ethereum",
    "solana": "solana",
    "dogecoin": "dogecoin",
    "xrp": "ripple",
    "cardano": "cardano",
    "polygon": "matic-network",
    "avalanche": "avalanche-2",
    "chainlink": "chainlink",
    "polkadot": "polkadot",
    "uniswap": "uniswap",
    "litecoin": "litecoin",
}


class MarketDataSignalGenerator(SignalGenerator):
    """Generates signals based on external crypto market data."""

    def __init__(self, coingecko_api_key: Optional[str] = None):
        super().__init__("market_data")
        self.coingecko_api_key = coingecko_api_key
        self._http_client: Optional[httpx.AsyncClient] = None
        self._price_cache: dict[str, dict] = {}
        self._cache_time: Optional[datetime] = None

    async def initialize(self):
        """Initialize the generator."""
        self._http_client = httpx.AsyncClient(timeout=30.0)
        logger.info("Market data signal generator initialized")

    async def shutdown(self):
        """Clean up resources."""
        if self._http_client:
            await self._http_client.aclose()

    async def generate(self, context: MarketContext) -> Optional[Signal]:
        """Generate a signal based on external market data."""
        features = {}

        # Extract asset from market
        asset = self._extract_asset(context.question, context.description)
        if not asset:
            return None

        features["detected_asset"] = asset

        # Get external price data
        price_data = await self._get_price_data(asset)
        if not price_data:
            return None

        features.update(price_data)

        # Analyze price movements
        direction, strength = self._analyze_price_movements(price_data)

        # Get market correlation
        correlation = self._analyze_market_correlation(
            context.current_price,
            context.price_history,
            price_data,
        )
        features["correlation"] = correlation

        # Determine if external price movement suggests Polymarket price should move
        if direction == SignalDirection.BULLISH:
            # If crypto price is up, and market is about price going up, bullish
            if self._is_price_up_market(context.question):
                predicted_prob = min(context.current_price + (strength * 0.15), 0.99)
            else:
                predicted_prob = max(context.current_price - (strength * 0.15), 0.01)
                direction = SignalDirection.BEARISH
        elif direction == SignalDirection.BEARISH:
            if self._is_price_up_market(context.question):
                predicted_prob = max(context.current_price - (strength * 0.15), 0.01)
            else:
                predicted_prob = min(context.current_price + (strength * 0.15), 0.99)
                direction = SignalDirection.BULLISH
        else:
            predicted_prob = context.current_price

        # Confidence based on correlation and data quality
        confidence = 0.5
        if abs(correlation) > 0.5:
            confidence += 0.2
        if price_data.get("volume_24h", 0) > 1_000_000_000:  # High volume = reliable data
            confidence += 0.1

        confidence = min(confidence, 0.85)

        reasoning = self._generate_reasoning(features, direction, asset)

        return self._create_signal(
            context=context,
            direction=direction,
            strength=strength,
            confidence=confidence,
            predicted_probability=predicted_prob,
            features=features,
            reasoning=reasoning,
        )

    def _extract_asset(self, question: str, description: str) -> Optional[str]:
        """Extract cryptocurrency asset from market text."""
        text = f"{question} {description}".lower()

        for asset, coingecko_id in ASSET_TO_COINGECKO.items():
            if asset in text:
                return asset

        # Check for ticker symbols
        tickers = {
            "btc": "bitcoin",
            "eth": "ethereum",
            "sol": "solana",
            "doge": "dogecoin",
            "ada": "cardano",
            "matic": "polygon",
            "avax": "avalanche",
            "link": "chainlink",
            "dot": "polkadot",
            "ltc": "litecoin",
        }

        for ticker, asset in tickers.items():
            if f" {ticker} " in f" {text} " or text.startswith(f"{ticker} "):
                return asset

        return None

    async def _get_price_data(self, asset: str) -> Optional[dict]:
        """Get current price data from CoinGecko."""
        if not self._http_client:
            return None

        # Check cache (5 minute expiry)
        if self._cache_time and datetime.utcnow() - self._cache_time < timedelta(minutes=5):
            if asset in self._price_cache:
                return self._price_cache[asset]

        coingecko_id = ASSET_TO_COINGECKO.get(asset)
        if not coingecko_id:
            return None

        try:
            headers = {}
            if self.coingecko_api_key:
                headers["x-cg-demo-api-key"] = self.coingecko_api_key

            response = await self._http_client.get(
                f"https://api.coingecko.com/api/v3/coins/{coingecko_id}",
                params={
                    "localization": "false",
                    "tickers": "false",
                    "community_data": "false",
                    "developer_data": "false",
                },
                headers=headers,
            )

            if response.status_code == 429:
                logger.warning("CoinGecko rate limit hit")
                return self._price_cache.get(asset)

            if response.status_code != 200:
                logger.warning("CoinGecko API error", status=response.status_code)
                return None

            data = response.json()
            market_data = data.get("market_data", {})

            price_data = {
                "current_price_usd": market_data.get("current_price", {}).get("usd", 0),
                "price_change_24h": market_data.get("price_change_percentage_24h", 0),
                "price_change_7d": market_data.get("price_change_percentage_7d", 0),
                "price_change_30d": market_data.get("price_change_percentage_30d", 0),
                "ath_usd": market_data.get("ath", {}).get("usd", 0),
                "ath_change_percentage": market_data.get("ath_change_percentage", {}).get("usd", 0),
                "volume_24h": market_data.get("total_volume", {}).get("usd", 0),
                "market_cap": market_data.get("market_cap", {}).get("usd", 0),
                "circulating_supply": market_data.get("circulating_supply", 0),
                "high_24h": market_data.get("high_24h", {}).get("usd", 0),
                "low_24h": market_data.get("low_24h", {}).get("usd", 0),
            }

            # Update cache
            self._price_cache[asset] = price_data
            self._cache_time = datetime.utcnow()

            return price_data

        except Exception as e:
            logger.error("Failed to get price data", asset=asset, error=str(e))
            return None

    def _analyze_price_movements(
        self,
        price_data: dict,
    ) -> tuple[SignalDirection, float]:
        """Analyze price movements to determine direction and strength."""
        change_24h = price_data.get("price_change_24h", 0)
        change_7d = price_data.get("price_change_7d", 0)

        # Weight recent changes more
        weighted_change = (change_24h * 0.7) + (change_7d / 7 * 0.3)

        if weighted_change > 3:
            direction = SignalDirection.BULLISH
            strength = min(weighted_change / 10, 1.0)
        elif weighted_change < -3:
            direction = SignalDirection.BEARISH
            strength = min(abs(weighted_change) / 10, 1.0)
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.3

        return direction, strength

    def _analyze_market_correlation(
        self,
        current_polymarket_price: float,
        polymarket_history: list[float],
        price_data: dict,
    ) -> float:
        """Analyze correlation between Polymarket price and external price."""
        # This is a simplified correlation analysis
        # In production, you would want historical external prices too

        if len(polymarket_history) < 5:
            return 0.0

        # Check if Polymarket price movement matches external price direction
        polymarket_change = (current_polymarket_price - polymarket_history[0]) / polymarket_history[0] * 100
        external_change = price_data.get("price_change_24h", 0)

        # Simple directional correlation
        if polymarket_change * external_change > 0:
            correlation = 0.7
        elif polymarket_change * external_change < 0:
            correlation = -0.3
        else:
            correlation = 0.0

        return correlation

    def _is_price_up_market(self, question: str) -> bool:
        """Determine if the market is betting on price going up."""
        question_lower = question.lower()

        up_keywords = [
            "above", "over", "exceed", "reach", "hit", "break",
            "surpass", "rise", "increase", "higher", "ath", "all-time high",
        ]

        down_keywords = [
            "below", "under", "fall", "drop", "crash", "decline",
            "decrease", "lower", "dip",
        ]

        up_count = sum(1 for kw in up_keywords if kw in question_lower)
        down_count = sum(1 for kw in down_keywords if kw in question_lower)

        return up_count >= down_count

    def _generate_reasoning(
        self,
        features: dict,
        direction: SignalDirection,
        asset: str,
    ) -> str:
        """Generate reasoning for the signal."""
        parts = [f"Asset: {asset.upper()}"]

        current_price = features.get("current_price_usd", 0)
        if current_price:
            parts.append(f"Price: ${current_price:,.2f}")

        change_24h = features.get("price_change_24h", 0)
        if change_24h:
            parts.append(f"24h change: {change_24h:+.2f}%")

        change_7d = features.get("price_change_7d", 0)
        if change_7d:
            parts.append(f"7d change: {change_7d:+.2f}%")

        volume = features.get("volume_24h", 0)
        if volume:
            parts.append(f"24h volume: ${volume/1e9:.2f}B")

        correlation = features.get("correlation", 0)
        if correlation:
            parts.append(f"Correlation: {correlation:.2f}")

        return f"{direction.value.upper()}: " + "; ".join(parts)
