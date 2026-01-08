"""
TradeEdge Pro - Probabilistic Market Regime Engine (V2.0)

Upgrades rule-based buckets to probability vectors for smoother transitions.

Metrics Used:
- ADX: Trend strength (14-period)
- Choppiness Index: Trendiness vs consolidation
- Hurst Exponent: Long-term memory (trend vs mean-reversion)
- ATR Percentile: Volatility rank vs 252-day history
"""
import pandas as pd
import numpy as np
import pandas_ta as ta
from dataclasses import dataclass
from typing import Dict, Optional
from enum import Enum

from app.utils.logger import get_logger

logger = get_logger(__name__)


class MarketRegime(str, Enum):
    """Market regime classification"""
    TRENDING = "TRENDING"
    RANGING = "RANGING"
    VOLATILE = "VOLATILE"
    DEAD = "DEAD"


@dataclass
class RegimeVector:
    """
    Probabilistic regime classification.
    
    Instead of a single label, returns probability distribution:
    {"TRENDING": 0.62, "RANGING": 0.18, "VOLATILE": 0.15, "DEAD": 0.05}
    """
    probabilities: Dict[str, float]
    dominant: MarketRegime
    confidence: float  # Probability of dominant regime
    
    # Supporting metrics
    adx: float
    choppiness: float
    hurst: float
    atr_percentile: float
    ema_slope: float
    
    def to_dict(self) -> dict:
        return {
            "probabilities": {k: round(v, 3) for k, v in self.probabilities.items()},
            "dominant": self.dominant.value,
            "confidence": round(self.confidence, 3),
            "metrics": {
                "adx": round(self.adx, 1),
                "choppiness": round(self.choppiness, 1),
                "hurst": round(self.hurst, 3),
                "atrPercentile": round(self.atr_percentile, 1),
                "emaSlope": round(self.ema_slope, 4),
            }
        }
    
    def get_position_multiplier(self) -> float:
        """
        Calculate position size multiplier based on regime probabilities.
        
        Weights:
        - TRENDING: 1.0 (full size)
        - RANGING: 0.6 (reduced)
        - VOLATILE: 0.5 (reduced)
        - DEAD: 0.0 (no trade)
        """
        multipliers = {
            "TRENDING": 1.0,
            "RANGING": 0.6,
            "VOLATILE": 0.5,
            "DEAD": 0.0
        }
        
        weighted_sum = sum(
            self.probabilities.get(regime, 0) * mult
            for regime, mult in multipliers.items()
        )
        return round(weighted_sum, 2)
    
    def get_score_adjustment(self) -> int:
        """
        Calculate score adjustment based on regime probabilities.
        
        Bonuses/Penalties:
        - TRENDING: +10
        - RANGING: -20
        - VOLATILE: 0
        - DEAD: -30
        """
        adjustments = {
            "TRENDING": 10,
            "RANGING": -20,
            "VOLATILE": 0,
            "DEAD": -30
        }
        
        weighted_adj = sum(
            self.probabilities.get(regime, 0) * adj
            for regime, adj in adjustments.items()
        )
        return int(round(weighted_adj))


def calculate_hurst_exponent(series: pd.Series, max_lag: int = 20) -> float:
    """
    Calculate Hurst Exponent using R/S analysis.
    
    Interpretation:
    - H > 0.5: Trending (persistent)
    - H = 0.5: Random walk
    - H < 0.5: Mean-reverting (anti-persistent)
    """
    if len(series) < max_lag * 2:
        return 0.5  # Default to random walk if insufficient data
    
    try:
        lags = range(2, max_lag)
        tau = []
        
        for lag in lags:
            # Calculate log returns
            returns = np.log(series / series.shift(lag)).dropna()
            if len(returns) < 2:
                continue
            
            # R/S calculation
            mean_ret = returns.mean()
            std_ret = returns.std()
            
            if std_ret == 0:
                continue
            
            cumdev = (returns - mean_ret).cumsum()
            r = cumdev.max() - cumdev.min()
            s = std_ret
            
            if s > 0 and r > 0:
                tau.append(r / s)
        
        if len(tau) < 3:
            return 0.5
        
        # Linear regression to estimate H
        log_lags = np.log(list(lags[:len(tau)]))
        log_tau = np.log(tau)
        
        slope, _ = np.polyfit(log_lags, log_tau, 1)
        
        # Clamp to reasonable range
        return max(0.1, min(0.9, slope))
    
    except Exception as e:
        logger.debug(f"Hurst calculation failed: {e}")
        return 0.5


def calculate_choppiness(df: pd.DataFrame, length: int = 14) -> float:
    """
    Calculate Choppiness Index.
    
    Interpretation:
    - > 61.8: Choppy/Ranging market
    - < 38.2: Trending market
    - Between: Transitional
    """
    if len(df) < length:
        return 50.0
    
    try:
        high = df['High'].tail(length)
        low = df['Low'].tail(length)
        close = df['Close'].tail(length)
        
        # True Range sum
        tr_sum = 0
        for i in range(1, length):
            tr = max(
                high.iloc[i] - low.iloc[i],
                abs(high.iloc[i] - close.iloc[i-1]),
                abs(low.iloc[i] - close.iloc[i-1])
            )
            tr_sum += tr
        
        # Highest high - Lowest low
        hh = high.max()
        ll = low.min()
        
        if hh == ll or tr_sum == 0:
            return 50.0
        
        chop = 100 * np.log10(tr_sum / (hh - ll)) / np.log10(length)
        return max(0, min(100, chop))
    
    except Exception as e:
        logger.debug(f"Choppiness calculation failed: {e}")
        return 50.0


def calculate_atr_percentile(df: pd.DataFrame, lookback: int = 252) -> float:
    """
    Calculate current ATR as percentile vs historical ATR.
    
    Returns:
        0-100 percentile (100 = highest volatility in lookback period)
    """
    if len(df) < lookback:
        lookback = len(df)
    
    if lookback < 20:
        return 50.0
    
    try:
        atr = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        if atr is None or len(atr) < lookback:
            return 50.0
        
        current_atr = atr.iloc[-1]
        historical_atr = atr.tail(lookback)
        
        percentile = (historical_atr < current_atr).sum() / len(historical_atr) * 100
        return percentile
    
    except Exception as e:
        logger.debug(f"ATR percentile calculation failed: {e}")
        return 50.0


def softmax(scores: Dict[str, float], temperature: float = 1.0) -> Dict[str, float]:
    """Apply softmax to convert raw scores to probabilities."""
    # Avoid overflow
    max_score = max(scores.values())
    exp_scores = {k: np.exp((v - max_score) / temperature) for k, v in scores.items()}
    total = sum(exp_scores.values())
    
    if total == 0:
        # Equal distribution if all zeros
        n = len(scores)
        return {k: 1/n for k in scores.keys()}
    
    return {k: v / total for k, v in exp_scores.items()}


def classify_regime_v2(df: pd.DataFrame) -> RegimeVector:
    """
    Classify market regime using probabilistic multi-factor approach.
    
    Factors:
    1. ADX (trend strength)
    2. Choppiness Index (fractal complexity)
    3. Hurst Exponent (mean-reversion vs trending)
    4. ATR Percentile (volatility rank)
    
    Returns:
        RegimeVector with probability distribution and supporting metrics
    """
    if len(df) < 50:
        return _default_regime_vector()
    
    df = df.copy()
    
    # === Calculate Metrics ===
    
    # 1. ADX
    adx_data = ta.adx(df['High'], df['Low'], df['Close'], length=14)
    adx = adx_data['ADX_14'].iloc[-1] if adx_data is not None else 20.0
    
    # 2. Choppiness Index
    choppiness = calculate_choppiness(df)
    
    # 3. Hurst Exponent
    hurst = calculate_hurst_exponent(df['Close'])
    
    # 4. ATR Percentile
    atr_percentile = calculate_atr_percentile(df)
    
    # 5. EMA Slope
    ema20 = ta.ema(df['Close'], length=20)
    if ema20 is not None and len(ema20) >= 10:
        ema_slope = (ema20.iloc[-1] - ema20.iloc[-10]) / ema20.iloc[-10]
    else:
        ema_slope = 0.0
    
    # === Calculate Raw Scores for Each Regime ===
    
    scores = {
        "TRENDING": 0.0,
        "RANGING": 0.0,
        "VOLATILE": 0.0,
        "DEAD": 0.0
    }
    
    # TRENDING score
    # High ADX, low choppiness, Hurst > 0.5
    trending_score = 0
    if adx > 25:
        trending_score += (adx - 25) * 2
    if choppiness < 50:
        trending_score += (50 - choppiness) * 1.5
    if hurst > 0.5:
        trending_score += (hurst - 0.5) * 100
    if abs(ema_slope) > 0.02:
        trending_score += 20
    scores["TRENDING"] = max(0, trending_score)
    
    # RANGING score
    # Low ADX, high choppiness, Hurst around 0.5
    ranging_score = 0
    if adx < 25:
        ranging_score += (25 - adx) * 2
    if choppiness > 50:
        ranging_score += (choppiness - 50) * 1.5
    if 0.4 < hurst < 0.6:
        ranging_score += 30
    if abs(ema_slope) < 0.01:
        ranging_score += 15
    scores["RANGING"] = max(0, ranging_score)
    
    # VOLATILE score
    # High ATR percentile, erratic movement
    volatile_score = 0
    if atr_percentile > 70:
        volatile_score += (atr_percentile - 70) * 2
    if choppiness > 60:
        volatile_score += (choppiness - 60)
    if adx > 20:  # Can be volatile with trend
        volatile_score += 10
    scores["VOLATILE"] = max(0, volatile_score)
    
    # DEAD score
    # Low ATR percentile, low ADX
    dead_score = 0
    if atr_percentile < 20:
        dead_score += (20 - atr_percentile) * 2.5
    if adx < 15:
        dead_score += (15 - adx) * 3
    if abs(ema_slope) < 0.005:
        dead_score += 20
    scores["DEAD"] = max(0, dead_score)
    
    # === Convert to Probabilities ===
    probabilities = softmax(scores, temperature=0.8)
    
    # Determine dominant regime
    dominant_regime = max(probabilities.items(), key=lambda x: x[1])
    dominant = MarketRegime(dominant_regime[0])
    confidence = dominant_regime[1]
    
    return RegimeVector(
        probabilities=probabilities,
        dominant=dominant,
        confidence=confidence,
        adx=adx,
        choppiness=choppiness,
        hurst=hurst,
        atr_percentile=atr_percentile,
        ema_slope=ema_slope
    )


def _default_regime_vector() -> RegimeVector:
    """Return default regime vector when data is insufficient."""
    return RegimeVector(
        probabilities={"TRENDING": 0.25, "RANGING": 0.25, "VOLATILE": 0.25, "DEAD": 0.25},
        dominant=MarketRegime.RANGING,
        confidence=0.25,
        adx=20.0,
        choppiness=50.0,
        hurst=0.5,
        atr_percentile=50.0,
        ema_slope=0.0
    )


def get_nifty_regime_v2() -> RegimeVector:
    """
    Get probabilistic regime analysis for NIFTY50.
    
    Returns:
        RegimeVector with probability distribution
    """
    try:
        import yfinance as yf
        
        nifty = yf.download("^NSEI", period="1y", progress=False)
        if nifty.empty:
            return _default_regime_vector()
        
        # Handle MultiIndex columns
        if isinstance(nifty.columns, pd.MultiIndex):
            nifty.columns = nifty.columns.droplevel(1)
        
        regime = classify_regime_v2(nifty)
        
        logger.info(
            f"NIFTY Regime V2: {regime.dominant.value} ({regime.confidence:.1%}) | "
            f"ADX={regime.adx:.1f}, Chop={regime.choppiness:.1f}, Hurst={regime.hurst:.2f}"
        )
        
        return regime
    
    except Exception as e:
        logger.warning(f"Failed to get NIFTY regime V2: {e}")
        return _default_regime_vector()
