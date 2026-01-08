"""
TradeEdge Pro - Base Strategy
Abstract base class with validation and backtest hooks
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Literal
from datetime import datetime
import pandas as pd
import pandas_ta as ta

from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class Signal:
    """Trading signal data class with enhanced metadata"""
    symbol: str
    signal_type: Literal["BUY", "SELL"]
    strategy: str
    entry_low: float
    entry_high: float
    stop_loss: float
    targets: List[float]
    score: int = 0
    trend_strength: str = "Neutral"
    risk_reward: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    valid_until: str = "Next market close"
    
    # Technical details
    ema_alignment: str = ""
    rsi_value: float = 0.0
    adx_value: float = 0.0
    volume_ratio: float = 0.0
    
    # === NEW METADATA FIELDS ===
    confidence: str = "Medium"          # High / Medium / Low
    market_regime: str = "NEUTRAL"      # TRENDING / RANGING / VOLATILE / DEAD
    entry_method: str = ""              # Breakout / Pullback / Support Bounce
    invalidated_if: str = ""            # "Close below 20 EMA"
    sector_rs: float = 1.0              # Sector relative strength
    
    def to_dict(self) -> dict:
        """Convert to API response format with enhanced metadata"""
        return {
            "symbol": self.symbol,
            "type": self.strategy,
            "signal": self.signal_type,
            "entry": {"low": self.entry_low, "high": self.entry_high},
            "stopLoss": self.stop_loss,
            "targets": self.targets,
            "score": self.score,
            "trendStrength": self.trend_strength,
            "riskReward": f"1:{self.risk_reward:.1f}",
            "timestamp": self.timestamp.isoformat(),
            "validUntil": self.valid_until,
            "technicals": {
                "emaAlignment": self.ema_alignment,
                "rsi": round(self.rsi_value, 1),
                "adx": round(self.adx_value, 1),
                "volumeRatio": round(self.volume_ratio, 2),
            },
            # New metadata for frontend UX
            "metadata": {
                "confidence": self.confidence,
                "marketRegime": self.market_regime,
                "entryMethod": self.entry_method,
                "invalidatedIf": self.invalidated_if,
                "sectorRs": round(self.sector_rs, 2),
            }
        }


@dataclass
class BacktestResult:
    """Backtest result data class"""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0


class BaseStrategy(ABC):
    """Abstract base class for trading strategies"""
    
    name: str = "base"
    
    def validate_data(self, df: pd.DataFrame) -> bool:
        """
        Validate DataFrame integrity before analysis.
        Hard gate - rejects invalid data silently with log warning.
        """
        if df is None or df.empty:
            logger.warning(f"{self.name}: Empty dataframe")
            return False
        
        if len(df) < settings.min_data_points:
            logger.warning(f"{self.name}: Insufficient data ({len(df)} < {settings.min_data_points})")
            return False
        
        required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
        if not all(col in df.columns for col in required_cols):
            logger.warning(f"{self.name}: Missing required columns")
            return False
        
        if df[required_cols].isna().any().any():
            logger.warning(f"{self.name}: NaN values detected")
            return False
        
        if not df.index.is_monotonic_increasing:
            logger.warning(f"{self.name}: Non-monotonic index")
            return False
        
        return True
    
    def add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add common technical indicators"""
        # EMAs
        df['EMA9'] = ta.ema(df['Close'], length=9)
        df['EMA21'] = ta.ema(df['Close'], length=21)
        df['EMA20'] = ta.ema(df['Close'], length=20)
        df['EMA50'] = ta.ema(df['Close'], length=50)
        
        # RSI
        df['RSI'] = ta.rsi(df['Close'], length=14)
        
        # ADX
        adx = ta.adx(df['High'], df['Low'], df['Close'], length=14)
        if adx is not None:
            df['ADX'] = adx['ADX_14']
            df['DI+'] = adx['DMP_14']
            df['DI-'] = adx['DMN_14']
        
        # MACD
        macd = ta.macd(df['Close'])
        if macd is not None:
            df['MACD'] = macd['MACD_12_26_9']
            df['MACD_Signal'] = macd['MACDs_12_26_9']
            df['MACD_Hist'] = macd['MACDh_12_26_9']
        
        # ATR for volatility and stops
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        df['ATR_PCT'] = (df['ATR'] / df['Close']) * 100
        
        # ATR percentile for dynamic volatility normalization
        df['ATR_20D_AVG'] = df['ATR'].rolling(20).mean()
        df['ATR_Percentile'] = df['ATR'] / df['ATR_20D_AVG']
        
        # Volume analysis
        df['Volume_SMA20'] = ta.sma(df['Volume'], length=20)
        df['Volume_Ratio'] = df['Volume'] / df['Volume_SMA20']
        
        return df
    
    def calculate_risk_reward(self, entry: float, stop_loss: float, target: float) -> float:
        """Calculate risk-reward ratio"""
        risk = abs(entry - stop_loss)
        if risk == 0:
            return 0
        reward = abs(target - entry)
        return reward / risk
    
    def get_trend_strength(self, df: pd.DataFrame) -> str:
        """Determine trend strength from indicators"""
        latest = df.iloc[-1]
        
        ema_aligned = latest['EMA9'] > latest['EMA21'] > latest['EMA50']
        adx_strong = latest.get('ADX', 0) > 25
        
        if ema_aligned and adx_strong:
            return "Strong"
        elif ema_aligned or adx_strong:
            return "Moderate"
        else:
            return "Weak"
    
    @abstractmethod
    def analyze(self, df: pd.DataFrame, symbol: str) -> Optional[Signal]:
        """
        Analyze data and generate signal.
        Must be implemented by subclasses.
        """
        pass
    
    def backtest(self, df: pd.DataFrame, symbol: str) -> BacktestResult:
        """Basic backtest implementation"""
        # TODO: Implement rolling window backtest
        return BacktestResult()
