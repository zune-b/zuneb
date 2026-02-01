"""Configuration management for the prediction machine."""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class PolymarketConfig(BaseSettings):
    """Polymarket API configuration."""

    api_key: str = Field(default="", alias="POLYMARKET_API_KEY")
    api_secret: str = Field(default="", alias="POLYMARKET_API_SECRET")
    private_key: str = Field(default="", alias="POLYMARKET_PRIVATE_KEY")

    class Config:
        env_file = ".env"


class TradingConfig(BaseSettings):
    """Trading configuration."""

    enabled: bool = Field(default=False, alias="TRADING_ENABLED")
    max_position_size: float = Field(default=100.0, alias="MAX_POSITION_SIZE")
    max_daily_loss: float = Field(default=500.0, alias="MAX_DAILY_LOSS")
    trade_interval_minutes: int = Field(default=15, alias="TRADE_INTERVAL_MINUTES")

    class Config:
        env_file = ".env"


class SignalWeights(BaseSettings):
    """Signal weights for ensemble predictions."""

    technical: float = Field(default=0.35, alias="WEIGHT_TECHNICAL")
    sentiment: float = Field(default=0.25, alias="WEIGHT_SENTIMENT")
    market_data: float = Field(default=0.25, alias="WEIGHT_MARKET_DATA")
    volatility: float = Field(default=0.15, alias="WEIGHT_VOLATILITY")

    class Config:
        env_file = ".env"

    def validate_weights(self) -> bool:
        """Ensure weights sum to 1.0."""
        total = self.technical + self.sentiment + self.market_data + self.volatility
        return abs(total - 1.0) < 0.001


class ThresholdConfig(BaseSettings):
    """Trading thresholds."""

    min_confidence: float = Field(default=0.65, alias="MIN_CONFIDENCE_THRESHOLD")
    min_edge: float = Field(default=0.05, alias="MIN_EDGE_THRESHOLD")

    class Config:
        env_file = ".env"


class ExternalAPIs(BaseSettings):
    """External API configurations."""

    coingecko_api_key: Optional[str] = Field(default=None, alias="COINGECKO_API_KEY")
    news_api_key: Optional[str] = Field(default=None, alias="NEWS_API_KEY")
    twitter_bearer_token: Optional[str] = Field(default=None, alias="TWITTER_BEARER_TOKEN")

    class Config:
        env_file = ".env"


class DatabaseConfig(BaseSettings):
    """Database configuration."""

    redis_url: str = Field(default="redis://localhost:6379", alias="REDIS_URL")
    database_url: str = Field(default="postgresql://localhost:5432/polymarket", alias="DATABASE_URL")

    class Config:
        env_file = ".env"


class Settings:
    """Main settings container."""

    def __init__(self):
        self.polymarket = PolymarketConfig()
        self.trading = TradingConfig()
        self.signal_weights = SignalWeights()
        self.thresholds = ThresholdConfig()
        self.external_apis = ExternalAPIs()
        self.database = DatabaseConfig()

    def validate(self) -> list[str]:
        """Validate all settings and return list of errors."""
        errors = []

        if not self.signal_weights.validate_weights():
            errors.append("Signal weights must sum to 1.0")

        if self.trading.enabled:
            if not self.polymarket.api_key:
                errors.append("POLYMARKET_API_KEY required when trading is enabled")
            if not self.polymarket.private_key:
                errors.append("POLYMARKET_PRIVATE_KEY required when trading is enabled")

        return errors


# Global settings instance
settings = Settings()
