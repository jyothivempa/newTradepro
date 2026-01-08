"""
TradeEdge Pro - Configuration Settings
"""
from pydantic_settings import BaseSettings
from typing import Literal
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # App Info
    app_name: str = "TradeEdge Pro"
    app_version: str = "1.0.0"
    debug: bool = False
    
    # Stock Universe
    stock_universe: Literal["NIFTY100", "NIFTY200", "NIFTY500"] = "NIFTY100"
    
    # Data Sources
    alpha_vantage_key: str = ""
    
    # Cache Settings
    redis_url: str = "redis://localhost:6379"
    cache_daily_ttl: int = 86400  # 24 hours
    cache_intraday_ttl: int = 900  # 15 minutes
    
    # Strategy Thresholds
    min_signal_score: int = 70
    min_risk_reward: float = 2.0
    max_stop_loss_pct: float = 5.0
    max_open_trades: int = 5
    
    # Data Validation
    min_data_points: int = 60
    max_retry_attempts: int = 3
    retry_delay_seconds: float = 1.0
    
    # Data Source Monitoring
    data_source_failure_threshold: int = 2  # Failures before auto-switch
    data_source_recovery_period: int = 300  # Seconds before retrying degraded source
    
    # Parallel Processing
    max_scan_workers: int = 20  # Default workers for signal scan
    adaptive_workers: bool = True  # Scale workers based on universe size
    
    # Feature Toggles (Optional Features)
    enable_options_hints: bool = False  # Show covered call hints for low-vol
    enable_economic_indicators: bool = False  # Use RBI data in regime
    
    # Telegram Alerts (optional)
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
