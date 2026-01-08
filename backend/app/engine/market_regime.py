"""
TradeEdge Pro - Market Regime Classification
Classifies market into TRENDING/RANGING/VOLATILE/DEAD for strategy filtering
"""
import pandas as pd
import numpy as np
import pandas_ta as ta
from dataclasses import dataclass
from typing import Literal, Tuple
from enum import Enum

from app.utils.logger import get_logger

logger = get_logger(__name__)


class MarketRegime(str, Enum):
    """Market regime classification"""
    TRENDING = "TRENDING"      # Strong directional movement
    RANGING = "RANGING"        # Oscillating, mean-reverting
    VOLATILE = "VOLATILE"      # High volatility, erratic
    DEAD = "DEAD"              # Low volatility, no movement


@dataclass
class RegimeAnalysis:
    """Detailed regime analysis with supporting metrics"""
    regime: MarketRegime
    adx: float
    atr_pct: float
    ema_slope: float
    trend_consistency: float
    confidence: float  # 0-100
    change_pct: float = 0.0  # Daily % change
    economic_bias: str = "neutral"  # "hawkish", "neutral", "dovish"
    
    def to_dict(self) -> dict:
        return {
            "regime": self.regime.value,
            "adx": round(self.adx, 1),
            "atrPct": round(self.atr_pct, 2),
            "emaSlope": round(self.ema_slope, 4),
            "trendConsistency": round(self.trend_consistency, 1),
            "confidence": round(self.confidence, 0),
            "changePct": round(self.change_pct, 2),
            "economicBias": self.economic_bias,
        }


def classify_regime(df: pd.DataFrame) -> RegimeAnalysis:
    """
    Classify market regime based on ADX, ATR%, and EMA slope.
    
    Criteria:
    - TRENDING: ADX > 25, consistent EMA slope, moderate ATR
    - RANGING: ADX < 20, price oscillating around mean
    - VOLATILE: ATR% > 2.5%, erratic price action
    - DEAD: ATR% < 0.5%, ADX < 15, no movement
    
    Returns:
        RegimeAnalysis with regime and supporting metrics
    """

    
    # Calculate indicators if not present
    if 'ADX' not in df.columns:
        adx_data = ta.adx(df['High'], df['Low'], df['Close'], length=14)
        if adx_data is not None:
            df['ADX'] = adx_data['ADX_14']
    
    if 'ATR' not in df.columns:
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
    
    if 'EMA20' not in df.columns:
        df['EMA20'] = ta.ema(df['Close'], length=20)
    
    df = df.dropna()
    if len(df) < 20:
        return RegimeAnalysis(
            regime=MarketRegime.RANGING,
            adx=0, atr_pct=0, ema_slope=0,
            trend_consistency=50, confidence=0
        )
    
    latest = df.iloc[-1]
    
    # Get metrics
    adx = latest.get('ADX', 20)
    atr = latest.get('ATR', 0)
    price = latest['Close']
    atr_pct = (atr / price) * 100 if price > 0 else 0
    
    # Calculate EMA slope (rate of change over last 10 bars)
    ema_recent = df['EMA20'].tail(10)
    if len(ema_recent) >= 2:
        ema_slope = (ema_recent.iloc[-1] - ema_recent.iloc[0]) / ema_recent.iloc[0]
    else:
        ema_slope = 0
    
    # Calculate trend consistency (% of bars moving in same direction)
    closes = df['Close'].tail(20)
    if len(closes) >= 2:
        changes = closes.diff().dropna()
        if ema_slope > 0:
            trend_consistency = (changes > 0).sum() / len(changes) * 100
        else:
            trend_consistency = (changes < 0).sum() / len(changes) * 100
    else:
        trend_consistency = 50
    
    # === REGIME CLASSIFICATION ===
    
    # DEAD market: Very low volatility and no trend
    if atr_pct < 0.5 and adx < 15:
        regime = MarketRegime.DEAD
        confidence = min(100, (15 - adx) * 5 + (0.5 - atr_pct) * 100)
    
    # VOLATILE market: High ATR%
    elif atr_pct > 2.5:
        regime = MarketRegime.VOLATILE
        confidence = min(100, (atr_pct - 2.5) * 40)
    
    # TRENDING market: Strong ADX + consistent slope
    elif adx > 25 and abs(ema_slope) > 0.01 and trend_consistency > 55:
        regime = MarketRegime.TRENDING
        confidence = min(100, (adx - 25) * 2 + trend_consistency - 50)
    
    # RANGING market: Low ADX, oscillating
    elif adx < 20:
        regime = MarketRegime.RANGING
        confidence = min(100, (20 - adx) * 3)
    
    # Default: Could be transitioning
    else:
        # Check which regime it's closest to
        if adx > 22 and trend_consistency > 50:
            regime = MarketRegime.TRENDING
            confidence = 40
        else:
            regime = MarketRegime.RANGING
            confidence = 40
    
    return RegimeAnalysis(
        regime=regime,
        adx=adx,
        atr_pct=atr_pct,
        ema_slope=ema_slope,
        trend_consistency=trend_consistency,
        confidence=confidence
    )


def get_suitable_strategies(regime: MarketRegime) -> list:
    """
    Get strategies suitable for the given market regime.
    
    Returns:
        List of strategy types that work well in this regime
    """
    strategy_map = {
        MarketRegime.TRENDING: ["breakout", "momentum", "pullback"],
        MarketRegime.RANGING: ["support_bounce", "mean_reversion"],
        MarketRegime.VOLATILE: ["momentum", "breakout"],
        MarketRegime.DEAD: [],  # No trades recommended
    }
    return strategy_map.get(regime, [])


def should_skip_entry(regime: MarketRegime, entry_method: str) -> Tuple[bool, str]:
    """
    Check if entry method should be skipped based on regime.
    
    Returns:
        (should_skip, reason)
    """
    skip_rules = {
        MarketRegime.DEAD: {
            "*": "Market is DEAD - no trading recommended"
        },
        MarketRegime.RANGING: {
            "Breakout": "Breakouts fail in ranging markets",
            "Momentum": "Momentum dies in ranging markets",
        },
        MarketRegime.VOLATILE: {
            "Pullback": "Pullbacks get stopped out in volatile markets",
            "Support Bounce": "Support levels break easily in volatile markets",
        },
        MarketRegime.TRENDING: {
            # Trending is good for most strategies
        }
    }
    
    regime_rules = skip_rules.get(regime, {})
    
    # Check for wildcard skip (all entries)
    if "*" in regime_rules:
        return True, regime_rules["*"]
    
    # Check specific entry method
    for method_key, reason in regime_rules.items():
        if method_key.lower() in entry_method.lower():
            return True, reason
    
    return False, ""


def get_regime_for_nifty() -> RegimeAnalysis:
    """
    Get market regime for NIFTY50 index.
    Cached for 15 minutes.
    """
    try:
        import yfinance as yf
        
        nifty = yf.download("^NSEI", period="3mo", progress=False)
        if nifty.empty:
            return RegimeAnalysis(
                regime=MarketRegime.RANGING,
                adx=0, atr_pct=0, ema_slope=0,
                trend_consistency=50, confidence=0,
                change_pct=0.0
            )
        
        # Handle MultiIndex columns
        if isinstance(nifty.columns, pd.MultiIndex):
            nifty.columns = nifty.columns.droplevel(1)
        
        regime = classify_regime(nifty)
        logger.info(f"NIFTY Regime: {regime.regime.value} (ADX: {regime.adx:.1f}, Change: {regime.change_pct:.2f}%)")
        return regime
    
    except Exception as e:
        logger.warning(f"Failed to get NIFTY regime: {e}")
        return RegimeAnalysis(
            regime=MarketRegime.RANGING,
            adx=0, atr_pct=0, ema_slope=0,
            trend_consistency=50, confidence=0,
            change_pct=0.0
        )

