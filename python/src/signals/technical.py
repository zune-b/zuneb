"""Technical analysis signal generator."""

import numpy as np
from typing import Optional
import structlog

from .base import SignalGenerator, Signal, SignalDirection, MarketContext

logger = structlog.get_logger()


class TechnicalSignalGenerator(SignalGenerator):
    """Generates signals based on technical analysis of price data."""

    def __init__(self):
        super().__init__("technical")
        self.min_history_points = 20

    async def initialize(self):
        """Initialize the generator."""
        logger.info("Technical signal generator initialized")

    async def shutdown(self):
        """Clean up resources."""
        pass

    async def generate(self, context: MarketContext) -> Optional[Signal]:
        """Generate a technical analysis signal."""
        if len(context.price_history) < self.min_history_points:
            logger.debug(
                "Insufficient price history",
                market_id=context.market_id,
                points=len(context.price_history),
            )
            return None

        prices = np.array(context.price_history)
        current_price = context.current_price

        # Calculate technical indicators
        features = {}

        # Moving averages
        ma_short = self._calculate_sma(prices, 5)
        ma_medium = self._calculate_sma(prices, 10)
        ma_long = self._calculate_sma(prices, 20)

        features["sma_5"] = ma_short
        features["sma_10"] = ma_medium
        features["sma_20"] = ma_long

        # RSI
        rsi = self._calculate_rsi(prices)
        features["rsi"] = rsi

        # MACD
        macd, signal_line, histogram = self._calculate_macd(prices)
        features["macd"] = macd
        features["macd_signal"] = signal_line
        features["macd_histogram"] = histogram

        # Bollinger Bands
        bb_upper, bb_middle, bb_lower = self._calculate_bollinger_bands(prices)
        features["bb_upper"] = bb_upper
        features["bb_middle"] = bb_middle
        features["bb_lower"] = bb_lower
        features["bb_position"] = (current_price - bb_lower) / (bb_upper - bb_lower) if bb_upper != bb_lower else 0.5

        # Momentum
        momentum = self._calculate_momentum(prices)
        features["momentum"] = momentum

        # Rate of change
        roc = self._calculate_roc(prices)
        features["roc"] = roc

        # Generate signal
        direction, strength, confidence = self._analyze_indicators(
            current_price, features
        )

        # Predict probability based on direction and strength
        if direction == SignalDirection.BULLISH:
            predicted_prob = current_price + (strength * 0.15)
        elif direction == SignalDirection.BEARISH:
            predicted_prob = current_price - (strength * 0.15)
        else:
            predicted_prob = current_price

        predicted_prob = min(max(predicted_prob, 0.01), 0.99)

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

    def _calculate_sma(self, prices: np.ndarray, period: int) -> float:
        """Calculate Simple Moving Average."""
        if len(prices) < period:
            return prices[-1]
        return float(np.mean(prices[-period:]))

    def _calculate_ema(self, prices: np.ndarray, period: int) -> float:
        """Calculate Exponential Moving Average."""
        if len(prices) < period:
            return prices[-1]

        multiplier = 2 / (period + 1)
        ema = prices[0]

        for price in prices[1:]:
            ema = (price - ema) * multiplier + ema

        return float(ema)

    def _calculate_rsi(self, prices: np.ndarray, period: int = 14) -> float:
        """Calculate Relative Strength Index."""
        if len(prices) < period + 1:
            return 50.0

        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return float(rsi)

    def _calculate_macd(
        self,
        prices: np.ndarray,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
    ) -> tuple[float, float, float]:
        """Calculate MACD indicator."""
        if len(prices) < slow:
            return 0.0, 0.0, 0.0

        ema_fast = self._calculate_ema(prices, fast)
        ema_slow = self._calculate_ema(prices, slow)

        macd = ema_fast - ema_slow

        # Calculate signal line (simplified)
        signal_line = macd * 0.9  # Approximation

        histogram = macd - signal_line

        return macd, signal_line, histogram

    def _calculate_bollinger_bands(
        self,
        prices: np.ndarray,
        period: int = 20,
        std_dev: float = 2.0,
    ) -> tuple[float, float, float]:
        """Calculate Bollinger Bands."""
        if len(prices) < period:
            return prices[-1] + 0.1, prices[-1], prices[-1] - 0.1

        middle = np.mean(prices[-period:])
        std = np.std(prices[-period:])

        upper = middle + (std_dev * std)
        lower = middle - (std_dev * std)

        return float(upper), float(middle), float(lower)

    def _calculate_momentum(self, prices: np.ndarray, period: int = 10) -> float:
        """Calculate momentum."""
        if len(prices) < period:
            return 0.0

        return float(prices[-1] - prices[-period])

    def _calculate_roc(self, prices: np.ndarray, period: int = 10) -> float:
        """Calculate Rate of Change."""
        if len(prices) < period or prices[-period] == 0:
            return 0.0

        return float((prices[-1] - prices[-period]) / prices[-period] * 100)

    def _analyze_indicators(
        self,
        current_price: float,
        features: dict,
    ) -> tuple[SignalDirection, float, float]:
        """Analyze indicators to determine direction, strength, and confidence."""
        bullish_signals = 0
        bearish_signals = 0
        total_weight = 0

        # Moving average analysis
        if current_price > features["sma_5"] > features["sma_10"]:
            bullish_signals += 2
        elif current_price < features["sma_5"] < features["sma_10"]:
            bearish_signals += 2
        total_weight += 2

        # RSI analysis
        rsi = features["rsi"]
        if rsi < 30:
            bullish_signals += 1.5  # Oversold
        elif rsi > 70:
            bearish_signals += 1.5  # Overbought
        elif rsi > 50:
            bullish_signals += 0.5
        else:
            bearish_signals += 0.5
        total_weight += 1.5

        # MACD analysis
        if features["macd_histogram"] > 0:
            bullish_signals += 1
        else:
            bearish_signals += 1
        total_weight += 1

        # Bollinger Bands analysis
        bb_pos = features["bb_position"]
        if bb_pos < 0.2:
            bullish_signals += 1  # Near lower band
        elif bb_pos > 0.8:
            bearish_signals += 1  # Near upper band
        total_weight += 1

        # Momentum analysis
        if features["momentum"] > 0:
            bullish_signals += 0.5
        else:
            bearish_signals += 0.5
        total_weight += 0.5

        # Determine direction
        if bullish_signals > bearish_signals * 1.2:
            direction = SignalDirection.BULLISH
            strength = min(bullish_signals / total_weight, 1.0)
        elif bearish_signals > bullish_signals * 1.2:
            direction = SignalDirection.BEARISH
            strength = min(bearish_signals / total_weight, 1.0)
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.3

        # Confidence based on agreement of signals
        agreement = abs(bullish_signals - bearish_signals) / total_weight
        confidence = 0.5 + (agreement * 0.5)

        return direction, strength, confidence

    def _generate_reasoning(
        self,
        features: dict,
        direction: SignalDirection,
    ) -> str:
        """Generate human-readable reasoning for the signal."""
        reasons = []

        rsi = features["rsi"]
        if rsi < 30:
            reasons.append(f"RSI oversold at {rsi:.1f}")
        elif rsi > 70:
            reasons.append(f"RSI overbought at {rsi:.1f}")

        if features["macd_histogram"] > 0:
            reasons.append("MACD bullish crossover")
        else:
            reasons.append("MACD bearish")

        bb_pos = features["bb_position"]
        if bb_pos < 0.2:
            reasons.append("Price near lower Bollinger Band")
        elif bb_pos > 0.8:
            reasons.append("Price near upper Bollinger Band")

        if features["momentum"] > 0.05:
            reasons.append(f"Strong positive momentum ({features['momentum']:.3f})")
        elif features["momentum"] < -0.05:
            reasons.append(f"Strong negative momentum ({features['momentum']:.3f})")

        return f"{direction.value.upper()}: " + "; ".join(reasons) if reasons else direction.value
