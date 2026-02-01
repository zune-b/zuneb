"""Base classes for signal generation."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any
from enum import Enum


class SignalDirection(Enum):
    """Direction of the signal."""

    BULLISH = "bullish"  # Expect YES probability to increase
    BEARISH = "bearish"  # Expect YES probability to decrease
    NEUTRAL = "neutral"  # No clear direction


@dataclass
class Signal:
    """Represents a trading signal from a signal generator."""

    source: str  # Name of the signal generator
    market_id: str
    direction: SignalDirection
    strength: float  # 0-1, how strong the signal is
    confidence: float  # 0-1, confidence in the signal
    predicted_probability: float  # 0-1, predicted YES probability
    features: dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def score(self) -> float:
        """Combined score of strength and confidence."""
        return self.strength * self.confidence

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "source": self.source,
            "market_id": self.market_id,
            "direction": self.direction.value,
            "strength": self.strength,
            "confidence": self.confidence,
            "predicted_probability": self.predicted_probability,
            "features": self.features,
            "reasoning": self.reasoning,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class MarketContext:
    """Context information for signal generation."""

    market_id: str
    question: str
    description: str
    current_price: float  # Current YES price
    volume_24h: float
    liquidity: float
    end_date: Optional[datetime]
    price_history: list[float] = field(default_factory=list)
    volume_history: list[float] = field(default_factory=list)
    timestamps: list[datetime] = field(default_factory=list)
    related_asset: Optional[str] = None  # e.g., "BTC", "ETH"
    category: str = "crypto"


class SignalGenerator(ABC):
    """Abstract base class for signal generators."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def generate(self, context: MarketContext) -> Optional[Signal]:
        """Generate a signal for a market.

        Args:
            context: Market context with relevant data

        Returns:
            Signal if one can be generated, None otherwise
        """
        pass

    @abstractmethod
    async def initialize(self):
        """Initialize the signal generator (load models, etc.)."""
        pass

    @abstractmethod
    async def shutdown(self):
        """Clean up resources."""
        pass

    def _create_signal(
        self,
        context: MarketContext,
        direction: SignalDirection,
        strength: float,
        confidence: float,
        predicted_probability: float,
        features: dict = None,
        reasoning: str = "",
    ) -> Signal:
        """Helper to create a signal."""
        return Signal(
            source=self.name,
            market_id=context.market_id,
            direction=direction,
            strength=min(max(strength, 0), 1),
            confidence=min(max(confidence, 0), 1),
            predicted_probability=min(max(predicted_probability, 0), 1),
            features=features or {},
            reasoning=reasoning,
        )
