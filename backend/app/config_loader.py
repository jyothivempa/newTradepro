"""
TradeEdge Pro - Configuration Management (V2.4)

Centralized YAML-based configuration with Pydantic validation.
"""
from typing import Dict, Literal
from pathlib import Path
import yaml
from pydantic import BaseModel, Field, ValidationError
from functools import lru_cache

from app.utils.logger import get_logger

logger = get_logger(__name__)

# Config file path
CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


# ===== Pydantic Models for Validation =====

class RiskConfig(BaseModel):
    """Risk management configuration"""
    daily_loss_limit_r: float = Field(2.0, gt=0, le=10)
    weekly_loss_limit_r: float = Field(6.0, gt=0, le=30)
    circuit_breaker_losses: int = Field(3, ge=2, le=10)
    max_open_trades: int = Field(5, ge=1, le=20)
    max_sector_exposure_pct: float = Field(30.0, gt=0, le=100)
    gap_tolerance: Dict[str, float] = Field(default_factory=dict)


class StrategyConfig(BaseModel):
    """Strategy thresholds"""
    min_risk_reward: float = Field(2.0, gt=0, le=10)
    max_stop_loss_pct: float = Field(5.0, gt=0, le=20)
    atr_multipliers: Dict[str, float] = Field(default_factory=dict)


class RegimeConfig(BaseModel):
    """Market regime controls"""
    kill_switch_limits: Dict[str, float] = Field(default_factory=dict)
    position_multipliers: Dict[str, float] = Field(default_factory=dict)


class DrawdownBracket(BaseModel):
    """Drawdown bracket definition"""
    threshold: float
    multiplier: float


class DrawdownConfig(BaseModel):
    """Drawdown scaling configuration"""
    brackets: list[DrawdownBracket]


class DataConfig(BaseModel):
    """Data fetching and caching"""
    min_data_points: int = Field(60, ge=20)
    max_retry_attempts: int = Field(3, ge=1, le=10)
    retry_delay_seconds: float = Field(1.0, gt=0, le=60)
    cache: Dict[str, int]


class ProcessingConfig(BaseModel):
    """Parallel processing settings"""
    max_scan_workers: int = Field(20, ge=1, le=100)
    adaptive_workers: bool = True


class WalkForwardConfig(BaseModel):
    """Walk-forward validation settings"""
    stability_threshold: float = Field(0.6, ge=0, le=1)
    min_expectancy: float = 0.0


class ExpectancyConfig(BaseModel):
    """Expectancy tracker settings"""
    rolling_window_trades: int = Field(50, ge=10, le=200)
    min_adequate_sample: int = Field(20, ge=5, le=100)
    default_win_rate: float = Field(0.40, ge=0, le=1)


class AppConfig(BaseModel):
    """Complete application configuration"""
    risk: RiskConfig
    strategy: StrategyConfig
    regime: RegimeConfig
    drawdown: DrawdownConfig
    data: DataConfig
    processing: ProcessingConfig
    walkforward: WalkForwardConfig
    expectancy: ExpectancyConfig


# ===== Configuration Loader =====

@lru_cache()
def load_config() -> AppConfig:
    """
    Load and validate configuration from config.yaml.
    
    Returns:
        AppConfig: Validated configuration object
        
    Raises:
        ValidationError: If configuration is invalid
        FileNotFoundError: If config.yaml not found
    """
    if not CONFIG_PATH.exists():
        logger.error(f"Configuration file not found: {CONFIG_PATH}")
        raise FileNotFoundError(f"config.yaml not found at {CONFIG_PATH}")
    
    try:
        with open(CONFIG_PATH, 'r') as f:
            raw_config = yaml.safe_load(f)
        
        # Validate with Pydantic
        config = AppConfig(**raw_config)
        
        logger.info(f"✅ Configuration loaded and validated from {CONFIG_PATH}")
        return config
        
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse YAML: {e}")
        raise
    except ValidationError as e:
        logger.error(f"Configuration validation failed: {e}")
        raise


# ===== Convenience Accessors =====

def get_risk_config() -> RiskConfig:
    """Get risk management configuration"""
    return load_config().risk


def get_strategy_config() -> StrategyConfig:
    """Get strategy configuration"""
    return load_config().strategy


def get_regime_config() -> RegimeConfig:
    """Get regime configuration"""
    return load_config().regime


# Backward compatibility: Maintain legacy Settings for secrets
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """
    Environment-based settings for secrets and runtime config.
    Use config.yaml for business logic thresholds.
    """
    # App Info
    app_name: str = "TradeEdge Pro"
    app_version: str = "2.4.0"
    environment: Literal["production", "development"] = "development"
    debug: bool = False
    
    # Stock Universe
    stock_universe: Literal["NIFTY100", "NIFTY200", "NIFTY500"] = "NIFTY100"
    
    # Secrets (from .env)
    alpha_vantage_key: str = ""
    redis_url: str = "redis://localhost:6379"
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Get environment-based settings (secrets only)"""
    return Settings()
