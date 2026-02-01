"""Ensemble predictor that combines multiple signals."""

import asyncio
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime
import structlog

from .base import Signal, SignalDirection, SignalGenerator, MarketContext
from .technical import TechnicalSignalGenerator
from .sentiment import SentimentSignalGenerator
from .market_data import MarketDataSignalGenerator
from .volatility import VolatilitySignalGenerator
from ..polymarket.trading import TradeSignal, TradeAction

logger = structlog.get_logger()


@dataclass
class EnsemblePrediction:
    """Combined prediction from all signal generators."""

    market_id: str
    signals: list[Signal]
    direction: SignalDirection
    combined_confidence: float
    predicted_probability: float
    expected_edge: float
    current_price: float
    recommended_action: TradeAction
    reasoning: str
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_trade_signal(self, size_recommendation: float = 10.0) -> TradeSignal:
        """Convert to a TradeSignal for execution."""
        return TradeSignal(
            market_id=self.market_id,
            action=self.recommended_action,
            confidence=self.combined_confidence,
            predicted_probability=self.predicted_probability,
            current_price=self.current_price,
            expected_edge=self.expected_edge,
            size_recommendation=size_recommendation,
            reasoning=self.reasoning,
        )


class EnsemblePredictor:
    """Combines multiple signal generators into ensemble predictions."""

    def __init__(
        self,
        weights: Optional[dict[str, float]] = None,
        news_api_key: Optional[str] = None,
        coingecko_api_key: Optional[str] = None,
    ):
        # Default weights
        self.weights = weights or {
            "technical": 0.35,
            "sentiment": 0.25,
            "market_data": 0.25,
            "volatility": 0.15,
        }

        # Initialize signal generators
        self.generators: dict[str, SignalGenerator] = {
            "technical": TechnicalSignalGenerator(),
            "sentiment": SentimentSignalGenerator(news_api_key=news_api_key),
            "market_data": MarketDataSignalGenerator(coingecko_api_key=coingecko_api_key),
            "volatility": VolatilitySignalGenerator(),
        }

        self._initialized = False

    async def initialize(self):
        """Initialize all signal generators."""
        if self._initialized:
            return

        await asyncio.gather(
            *[gen.initialize() for gen in self.generators.values()]
        )

        self._initialized = True
        logger.info(
            "Ensemble predictor initialized",
            generators=list(self.generators.keys()),
            weights=self.weights,
        )

    async def shutdown(self):
        """Shutdown all signal generators."""
        await asyncio.gather(
            *[gen.shutdown() for gen in self.generators.values()]
        )
        self._initialized = False

    async def predict(self, context: MarketContext) -> Optional[EnsemblePrediction]:
        """Generate an ensemble prediction for a market."""
        if not self._initialized:
            await self.initialize()

        # Generate signals from all generators concurrently
        signal_tasks = {
            name: gen.generate(context)
            for name, gen in self.generators.items()
        }

        results = await asyncio.gather(
            *signal_tasks.values(),
            return_exceptions=True,
        )

        # Collect successful signals
        signals: list[Signal] = []
        for name, result in zip(signal_tasks.keys(), results):
            if isinstance(result, Exception):
                logger.warning(
                    "Signal generation failed",
                    generator=name,
                    error=str(result),
                )
            elif result is not None:
                signals.append(result)

        if not signals:
            logger.debug(
                "No signals generated for market",
                market_id=context.market_id,
            )
            return None

        # Combine signals
        prediction = self._combine_signals(signals, context)

        logger.info(
            "Generated ensemble prediction",
            market_id=context.market_id,
            direction=prediction.direction.value,
            confidence=prediction.combined_confidence,
            edge=prediction.expected_edge,
            action=prediction.recommended_action.value,
            signal_count=len(signals),
        )

        return prediction

    async def predict_batch(
        self,
        contexts: list[MarketContext],
        max_concurrent: int = 5,
    ) -> list[EnsemblePrediction]:
        """Generate predictions for multiple markets."""
        predictions = []

        # Process in batches
        for i in range(0, len(contexts), max_concurrent):
            batch = contexts[i:i + max_concurrent]
            batch_results = await asyncio.gather(
                *[self.predict(ctx) for ctx in batch],
                return_exceptions=True,
            )

            for result in batch_results:
                if isinstance(result, EnsemblePrediction):
                    predictions.append(result)

        return predictions

    def _combine_signals(
        self,
        signals: list[Signal],
        context: MarketContext,
    ) -> EnsemblePrediction:
        """Combine multiple signals into an ensemble prediction."""
        # Calculate weighted scores for each direction
        bullish_score = 0.0
        bearish_score = 0.0
        neutral_score = 0.0
        total_weight = 0.0

        weighted_probabilities = []
        weighted_confidences = []

        for signal in signals:
            weight = self.weights.get(signal.source, 0.0)
            if weight == 0:
                continue

            total_weight += weight
            effective_weight = weight * signal.confidence

            if signal.direction == SignalDirection.BULLISH:
                bullish_score += signal.strength * effective_weight
            elif signal.direction == SignalDirection.BEARISH:
                bearish_score += signal.strength * effective_weight
            else:
                neutral_score += signal.strength * effective_weight

            weighted_probabilities.append(
                (signal.predicted_probability, effective_weight)
            )
            weighted_confidences.append((signal.confidence, weight))

        # Determine overall direction
        max_score = max(bullish_score, bearish_score, neutral_score)
        if max_score == bullish_score and bullish_score > bearish_score * 1.2:
            direction = SignalDirection.BULLISH
        elif max_score == bearish_score and bearish_score > bullish_score * 1.2:
            direction = SignalDirection.BEARISH
        else:
            direction = SignalDirection.NEUTRAL

        # Calculate weighted predicted probability
        if weighted_probabilities:
            prob_sum = sum(p * w for p, w in weighted_probabilities)
            weight_sum = sum(w for _, w in weighted_probabilities)
            predicted_probability = prob_sum / weight_sum if weight_sum > 0 else 0.5
        else:
            predicted_probability = context.current_price

        # Calculate combined confidence
        if weighted_confidences:
            conf_sum = sum(c * w for c, w in weighted_confidences)
            weight_sum = sum(w for _, w in weighted_confidences)
            base_confidence = conf_sum / weight_sum if weight_sum > 0 else 0.5
        else:
            base_confidence = 0.5

        # Adjust confidence based on signal agreement
        agreement = self._calculate_agreement(signals)
        combined_confidence = base_confidence * (0.7 + 0.3 * agreement)
        combined_confidence = min(max(combined_confidence, 0.1), 0.95)

        # Calculate expected edge
        expected_edge = predicted_probability - context.current_price

        # Determine recommended action
        recommended_action = self._determine_action(
            direction,
            expected_edge,
            combined_confidence,
            context.current_price,
        )

        # Generate reasoning
        reasoning = self._generate_reasoning(
            signals, direction, expected_edge, combined_confidence
        )

        return EnsemblePrediction(
            market_id=context.market_id,
            signals=signals,
            direction=direction,
            combined_confidence=combined_confidence,
            predicted_probability=predicted_probability,
            expected_edge=expected_edge,
            current_price=context.current_price,
            recommended_action=recommended_action,
            reasoning=reasoning,
        )

    def _calculate_agreement(self, signals: list[Signal]) -> float:
        """Calculate how much signals agree (0-1)."""
        if len(signals) <= 1:
            return 1.0

        directions = [s.direction for s in signals]
        most_common = max(set(directions), key=directions.count)
        agreement = directions.count(most_common) / len(directions)

        return agreement

    def _determine_action(
        self,
        direction: SignalDirection,
        expected_edge: float,
        confidence: float,
        current_price: float,
    ) -> TradeAction:
        """Determine the recommended trading action."""
        # Minimum thresholds
        MIN_EDGE = 0.03
        MIN_CONFIDENCE = 0.55

        if confidence < MIN_CONFIDENCE:
            return TradeAction.HOLD

        if abs(expected_edge) < MIN_EDGE:
            return TradeAction.HOLD

        if direction == SignalDirection.BULLISH:
            if expected_edge > 0:
                return TradeAction.BUY_YES
            else:
                return TradeAction.BUY_NO
        elif direction == SignalDirection.BEARISH:
            if expected_edge < 0:
                return TradeAction.BUY_NO
            else:
                return TradeAction.BUY_YES
        else:
            return TradeAction.HOLD

    def _generate_reasoning(
        self,
        signals: list[Signal],
        direction: SignalDirection,
        expected_edge: float,
        confidence: float,
    ) -> str:
        """Generate human-readable reasoning for the prediction."""
        parts = []

        # Direction summary
        parts.append(f"Direction: {direction.value.upper()}")
        parts.append(f"Edge: {expected_edge:+.2%}")
        parts.append(f"Confidence: {confidence:.1%}")

        # Signal summary
        parts.append(f"\nSignals ({len(signals)}):")
        for signal in signals:
            parts.append(
                f"  - {signal.source}: {signal.direction.value} "
                f"(strength={signal.strength:.2f}, conf={signal.confidence:.2f})"
            )

        # Key reasons from signals
        parts.append("\nKey factors:")
        for signal in signals:
            if signal.reasoning:
                parts.append(f"  - {signal.reasoning}")

        return "\n".join(parts)

    def get_weights(self) -> dict[str, float]:
        """Get current signal weights."""
        return self.weights.copy()

    def set_weights(self, weights: dict[str, float]):
        """Update signal weights."""
        # Validate weights sum to 1
        total = sum(weights.values())
        if abs(total - 1.0) > 0.001:
            # Normalize
            weights = {k: v / total for k, v in weights.items()}

        self.weights = weights
        logger.info("Updated signal weights", weights=weights)
