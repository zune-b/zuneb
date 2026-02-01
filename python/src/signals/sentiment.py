"""Sentiment analysis signal generator."""

import re
from typing import Optional
from datetime import datetime, timedelta
import httpx
import structlog

from .base import SignalGenerator, Signal, SignalDirection, MarketContext

logger = structlog.get_logger()


# Crypto-specific sentiment keywords
BULLISH_KEYWORDS = [
    "bullish", "moon", "pump", "rally", "breakout", "accumulate",
    "buy", "long", "hodl", "adoption", "institutional", "etf approved",
    "partnership", "upgrade", "halving", "ath", "all time high",
    "support holding", "golden cross", "bullrun", "bull run",
]

BEARISH_KEYWORDS = [
    "bearish", "dump", "crash", "sell", "short", "correction",
    "bear market", "rejection", "resistance", "death cross",
    "hack", "exploit", "rug pull", "scam", "sec lawsuit",
    "regulation", "ban", "fud", "capitulation", "breakdown",
]


class SentimentSignalGenerator(SignalGenerator):
    """Generates signals based on sentiment analysis."""

    def __init__(
        self,
        news_api_key: Optional[str] = None,
        twitter_bearer_token: Optional[str] = None,
    ):
        super().__init__("sentiment")
        self.news_api_key = news_api_key
        self.twitter_bearer_token = twitter_bearer_token
        self._http_client: Optional[httpx.AsyncClient] = None

    async def initialize(self):
        """Initialize the generator."""
        self._http_client = httpx.AsyncClient(timeout=30.0)
        logger.info("Sentiment signal generator initialized")

    async def shutdown(self):
        """Clean up resources."""
        if self._http_client:
            await self._http_client.aclose()

    async def generate(self, context: MarketContext) -> Optional[Signal]:
        """Generate a sentiment-based signal."""
        features = {}

        # Extract asset from market question
        asset = self._extract_asset(context.question, context.description)
        features["detected_asset"] = asset

        if not asset:
            logger.debug(
                "Could not detect crypto asset",
                market_id=context.market_id,
            )
            return None

        # Collect sentiment from various sources
        text_sentiment = await self._analyze_text_sentiment(
            context.question, context.description
        )
        features["text_sentiment"] = text_sentiment

        news_sentiment = await self._get_news_sentiment(asset)
        features["news_sentiment"] = news_sentiment

        # Aggregate sentiment scores
        sentiments = [s for s in [text_sentiment, news_sentiment] if s is not None]

        if not sentiments:
            return None

        avg_sentiment = sum(sentiments) / len(sentiments)
        features["avg_sentiment"] = avg_sentiment

        # Determine direction
        if avg_sentiment > 0.2:
            direction = SignalDirection.BULLISH
            strength = min(avg_sentiment, 1.0)
        elif avg_sentiment < -0.2:
            direction = SignalDirection.BEARISH
            strength = min(abs(avg_sentiment), 1.0)
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.3

        # Confidence based on number of sources and agreement
        confidence = 0.5 + (len(sentiments) * 0.1)
        if len(sentiments) > 1:
            variance = sum((s - avg_sentiment) ** 2 for s in sentiments) / len(sentiments)
            confidence -= min(variance, 0.2)

        confidence = min(max(confidence, 0.3), 0.9)

        # Predict probability
        predicted_prob = context.current_price + (avg_sentiment * 0.1)
        predicted_prob = min(max(predicted_prob, 0.01), 0.99)

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

        # Common crypto assets and their variations
        assets = {
            "bitcoin": ["bitcoin", "btc"],
            "ethereum": ["ethereum", "eth", "ether"],
            "solana": ["solana", "sol"],
            "dogecoin": ["dogecoin", "doge"],
            "xrp": ["xrp", "ripple"],
            "cardano": ["cardano", "ada"],
            "polygon": ["polygon", "matic"],
            "avalanche": ["avalanche", "avax"],
            "chainlink": ["chainlink", "link"],
            "polkadot": ["polkadot", "dot"],
            "uniswap": ["uniswap", "uni"],
            "litecoin": ["litecoin", "ltc"],
        }

        for asset, keywords in assets.items():
            for keyword in keywords:
                if keyword in text:
                    return asset

        # Generic crypto detection
        if any(word in text for word in ["crypto", "cryptocurrency", "token", "coin"]):
            return "crypto"

        return None

    async def _analyze_text_sentiment(
        self,
        question: str,
        description: str,
    ) -> float:
        """Analyze sentiment of market text using keyword matching."""
        text = f"{question} {description}".lower()

        bullish_count = sum(1 for kw in BULLISH_KEYWORDS if kw in text)
        bearish_count = sum(1 for kw in BEARISH_KEYWORDS if kw in text)

        total = bullish_count + bearish_count
        if total == 0:
            return 0.0

        # Score from -1 to 1
        score = (bullish_count - bearish_count) / total
        return score

    async def _get_news_sentiment(self, asset: str) -> Optional[float]:
        """Get sentiment from news articles."""
        if not self.news_api_key or not self._http_client:
            return None

        try:
            # Fetch recent news
            from_date = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")

            response = await self._http_client.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": f"{asset} crypto cryptocurrency",
                    "from": from_date,
                    "sortBy": "publishedAt",
                    "language": "en",
                    "pageSize": 20,
                    "apiKey": self.news_api_key,
                },
            )

            if response.status_code != 200:
                logger.warning("News API error", status=response.status_code)
                return None

            data = response.json()
            articles = data.get("articles", [])

            if not articles:
                return None

            # Analyze headlines and descriptions
            total_sentiment = 0.0
            count = 0

            for article in articles:
                headline = article.get("title", "")
                desc = article.get("description", "")
                text = f"{headline} {desc}".lower()

                bullish = sum(1 for kw in BULLISH_KEYWORDS if kw in text)
                bearish = sum(1 for kw in BEARISH_KEYWORDS if kw in text)

                if bullish + bearish > 0:
                    sentiment = (bullish - bearish) / (bullish + bearish)
                    total_sentiment += sentiment
                    count += 1

            if count == 0:
                return None

            return total_sentiment / count

        except Exception as e:
            logger.error("Failed to get news sentiment", error=str(e))
            return None

    async def _get_social_sentiment(self, asset: str) -> Optional[float]:
        """Get sentiment from social media (placeholder for Twitter/Reddit)."""
        # This would integrate with Twitter API, Reddit API, etc.
        # For now, return None as placeholder
        return None

    def _generate_reasoning(
        self,
        features: dict,
        direction: SignalDirection,
        asset: str,
    ) -> str:
        """Generate reasoning for the sentiment signal."""
        parts = [f"Asset: {asset}"]

        if features.get("text_sentiment") is not None:
            score = features["text_sentiment"]
            if score > 0:
                parts.append(f"Market text bullish ({score:.2f})")
            elif score < 0:
                parts.append(f"Market text bearish ({score:.2f})")

        if features.get("news_sentiment") is not None:
            score = features["news_sentiment"]
            if score > 0:
                parts.append(f"News sentiment bullish ({score:.2f})")
            elif score < 0:
                parts.append(f"News sentiment bearish ({score:.2f})")

        avg = features.get("avg_sentiment", 0)
        parts.append(f"Overall sentiment: {avg:.2f}")

        return f"{direction.value.upper()}: " + "; ".join(parts)
