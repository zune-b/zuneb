"""Volatility-based signal generator."""

import numpy as np
from typing import Optional
import structlog

from .base import SignalGenerator, Signal, SignalDirection, MarketContext

logger = structlog.get_logger()


class VolatilitySignalGenerator(SignalGenerator):
    """Generates signals based on volatility analysis."""

    def __init__(self):
        super().__init__("volatility")
        self.min_history_points = 15

    async def initialize(self):
        """Initialize the generator."""
        logger.info("Volatility signal generator initialized")

    async def shutdown(self):
        """Clean up resources."""
        pass

    async def generate(self, context: MarketContext) -> Optional[Signal]:
        """Generate a volatility-based signal."""
        if len(context.price_history) < self.min_history_points:
            logger.debug(
                "Insufficient price history for volatility analysis",
                market_id=context.market_id,
                points=len(context.price_history),
            )
            return None

        prices = np.array(context.price_history)
        current_price = context.current_price

        features = {}

        # Calculate volatility metrics
        returns = np.diff(prices) / prices[:-1]
        features["returns_mean"] = float(np.mean(returns))
        features["returns_std"] = float(np.std(returns))

        # Historical volatility
        hist_vol = self._calculate_historical_volatility(prices)
        features["historical_volatility"] = hist_vol

        # Realized volatility (recent)
        recent_vol = self._calculate_historical_volatility(prices[-10:]) if len(prices) >= 10 else hist_vol
        features["recent_volatility"] = recent_vol

        # Volatility ratio
        vol_ratio = recent_vol / hist_vol if hist_vol > 0 else 1.0
        features["volatility_ratio"] = vol_ratio

        # Average True Range (simplified for probabilities)
        atr = self._calculate_atr(prices)
        features["atr"] = atr

        # Volatility percentile
        vol_percentile = self._calculate_volatility_percentile(prices)
        features["volatility_percentile"] = vol_percentile

        # Price range analysis
        high = float(np.max(prices[-20:]))
        low = float(np.min(prices[-20:]))
        price_range = high - low
        features["price_range"] = price_range
        features["range_position"] = (current_price - low) / price_range if price_range > 0 else 0.5

        # Trend strength
        trend_strength = self._calculate_trend_strength(prices)
        features["trend_strength"] = trend_strength

        # Analyze and generate signal
        direction, strength, confidence = self._analyze_volatility(
            current_price, features, prices
        )

        # Predict probability based on volatility regime
        predicted_prob = self._predict_probability(
            current_price, direction, strength, features
        )

        reasoning = self._generate_reasoning(features, direction)

        return self._create_signal(
            context=context,
            direction=direction,
            strength=strength,
            confidence=confidence,
            predicted_probability=predicted_prob,
            features=features,
            reasoning=reasoning,
        )

    def _calculate_historical_volatility(
        self,
        prices: np.ndarray,
        annualization_factor: float = 1.0,
    ) -> float:
        """Calculate historical volatility."""
        if len(prices) < 2:
            return 0.0

        returns = np.diff(prices) / prices[:-1]
        vol = np.std(returns) * np.sqrt(annualization_factor)
        return float(vol)

    def _calculate_atr(self, prices: np.ndarray, period: int = 14) -> float:
        """Calculate Average True Range (simplified for single price series)."""
        if len(prices) < period:
            return float(np.std(prices))

        # Use price differences as a proxy for true range
        ranges = np.abs(np.diff(prices))
        atr = np.mean(ranges[-period:])
        return float(atr)

    def _calculate_volatility_percentile(
        self,
        prices: np.ndarray,
        lookback: int = 30,
    ) -> float:
        """Calculate current volatility as percentile of historical."""
        if len(prices) < lookback:
            return 50.0

        # Calculate rolling volatility
        rolling_vols = []
        window = 5

        for i in range(window, len(prices)):
            window_prices = prices[i-window:i]
            vol = self._calculate_historical_volatility(window_prices)
            rolling_vols.append(vol)

        if not rolling_vols:
            return 50.0

        current_vol = rolling_vols[-1]
        percentile = sum(1 for v in rolling_vols if v <= current_vol) / len(rolling_vols) * 100

        return float(percentile)

    def _calculate_trend_strength(self, prices: np.ndarray) -> float:
        """Calculate trend strength using linear regression."""
        if len(prices) < 5:
            return 0.0

        # Fit linear regression
        x = np.arange(len(prices))
        slope, _ = np.polyfit(x, prices, 1)

        # Normalize slope by price range
        price_range = np.max(prices) - np.min(prices)
        if price_range == 0:
            return 0.0

        trend_strength = slope * len(prices) / price_range
        return float(np.clip(trend_strength, -1, 1))

    def _analyze_volatility(
        self,
        current_price: float,
        features: dict,
        prices: np.ndarray,
    ) -> tuple[SignalDirection, float, float]:
        """Analyze volatility to determine direction and strength."""
        vol_ratio = features["volatility_ratio"]
        vol_percentile = features["volatility_percentile"]
        trend_strength = features["trend_strength"]
        range_position = features["range_position"]

        # Determine direction based on volatility regime and trend
        if vol_ratio > 1.5:
            # High volatility regime - expect mean reversion
            if range_position > 0.7:
                direction = SignalDirection.BEARISH
                strength = min((range_position - 0.5) * 2, 1.0)
            elif range_position < 0.3:
                direction = SignalDirection.BULLISH
                strength = min((0.5 - range_position) * 2, 1.0)
            else:
                direction = SignalDirection.NEUTRAL
                strength = 0.3
        elif vol_ratio < 0.5:
            # Low volatility regime - expect breakout in trend direction
            if trend_strength > 0.3:
                direction = SignalDirection.BULLISH
                strength = min(abs(trend_strength), 1.0)
            elif trend_strength < -0.3:
                direction = SignalDirection.BEARISH
                strength = min(abs(trend_strength), 1.0)
            else:
                direction = SignalDirection.NEUTRAL
                strength = 0.3
        else:
            # Normal volatility - follow trend
            if trend_strength > 0.2:
                direction = SignalDirection.BULLISH
                strength = min(abs(trend_strength) * 0.8, 0.8)
            elif trend_strength < -0.2:
                direction = SignalDirection.BEARISH
                strength = min(abs(trend_strength) * 0.8, 0.8)
            else:
                direction = SignalDirection.NEUTRAL
                strength = 0.3

        # Confidence based on consistency of signals
        confidence = 0.5

        # Higher confidence in extreme volatility percentiles
        if vol_percentile > 80 or vol_percentile < 20:
            confidence += 0.15

        # Higher confidence when trend and position align
        if (trend_strength > 0 and range_position < 0.4) or \
           (trend_strength < 0 and range_position > 0.6):
            confidence += 0.1

        # Lower confidence in neutral regimes
        if direction == SignalDirection.NEUTRAL:
            confidence -= 0.1

        confidence = min(max(confidence, 0.3), 0.85)

        return direction, strength, confidence

    def _predict_probability(
        self,
        current_price: float,
        direction: SignalDirection,
        strength: float,
        features: dict,
    ) -> float:
        """Predict probability based on volatility analysis."""
        atr = features["atr"]

        if direction == SignalDirection.BULLISH:
            move = atr * strength * 2
            predicted = current_price + move
        elif direction == SignalDirection.BEARISH:
            move = atr * strength * 2
            predicted = current_price - move
        else:
            predicted = current_price

        return float(np.clip(predicted, 0.01, 0.99))

    def _generate_reasoning(
        self,
        features: dict,
        direction: SignalDirection,
    ) -> str:
        """Generate reasoning for the volatility signal."""
        parts = []

        vol_ratio = features["volatility_ratio"]
        if vol_ratio > 1.5:
            parts.append(f"High volatility regime ({vol_ratio:.2f}x)")
        elif vol_ratio < 0.5:
            parts.append(f"Low volatility regime ({vol_ratio:.2f}x)")
        else:
            parts.append(f"Normal volatility ({vol_ratio:.2f}x)")

        vol_pct = features["volatility_percentile"]
        parts.append(f"Volatility percentile: {vol_pct:.0f}%")

        trend = features["trend_strength"]
        if trend > 0.2:
            parts.append(f"Uptrend ({trend:.2f})")
        elif trend < -0.2:
            parts.append(f"Downtrend ({trend:.2f})")

        range_pos = features["range_position"]
        if range_pos > 0.7:
            parts.append("Near range high")
        elif range_pos < 0.3:
            parts.append("Near range low")

        return f"{direction.value.upper()}: " + "; ".join(parts)
