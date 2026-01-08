"""
TradeEdge Pro - Professional Technical Indicators
Advanced indicators for institutional-grade trading signals
"""
import pandas as pd
import numpy as np
import pandas_ta as ta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SupportResistance:
    """Support/Resistance level with strength ranking"""
    level: float
    type: str  # "support" or "resistance"
    strength: int  # 1-5 (number of touches)
    distance_pct: float  # Distance from current price


@dataclass
class CandlePattern:
    """Candlestick pattern detection result"""
    name: str
    type: str  # "bullish" or "bearish"
    strength: int  # 1-3 (weak, moderate, strong)


def detect_support_resistance(
    df: pd.DataFrame,
    lookback: int = 60,
    tolerance_pct: float = 1.0,
) -> Tuple[List[SupportResistance], List[SupportResistance]]:
    """
    Detect support and resistance levels from swing highs/lows.
    
    Returns:
        (support_levels, resistance_levels) sorted by distance from current price
    """
    if len(df) < lookback:
        return [], []
    
    recent = df.tail(lookback).copy()
    current_price = recent['Close'].iloc[-1]
    
    # Find swing highs (local maxima) and swing lows (local minima)
    highs = recent['High'].values
    lows = recent['Low'].values
    
    swing_highs = []
    swing_lows = []
    
    # Detect swing points (5-bar pivot)
    for i in range(2, len(recent) - 2):
        # Swing high: higher than 2 bars on each side
        if highs[i] > max(highs[i-2:i]) and highs[i] > max(highs[i+1:i+3]):
            swing_highs.append(highs[i])
        
        # Swing low: lower than 2 bars on each side
        if lows[i] < min(lows[i-2:i]) and lows[i] < min(lows[i+1:i+3]):
            swing_lows.append(lows[i])
    
    # Cluster similar levels
    def cluster_levels(levels: List[float], tolerance: float) -> Dict[float, int]:
        if not levels:
            return {}
        
        levels = sorted(levels)
        clusters = {}
        current_cluster = [levels[0]]
        
        for level in levels[1:]:
            if abs(level - current_cluster[0]) / current_cluster[0] * 100 <= tolerance:
                current_cluster.append(level)
            else:
                avg_level = sum(current_cluster) / len(current_cluster)
                clusters[avg_level] = len(current_cluster)
                current_cluster = [level]
        
        # Add last cluster
        avg_level = sum(current_cluster) / len(current_cluster)
        clusters[avg_level] = len(current_cluster)
        
        return clusters
    
    # Cluster and create S/R objects
    resistance_clusters = cluster_levels(swing_highs, tolerance_pct)
    support_clusters = cluster_levels(swing_lows, tolerance_pct)
    
    support_levels = []
    resistance_levels = []
    
    for level, strength in support_clusters.items():
        if level < current_price:  # Valid support
            distance = ((current_price - level) / current_price) * 100
            support_levels.append(SupportResistance(
                level=round(level, 2),
                type="support",
                strength=min(strength, 5),
                distance_pct=round(distance, 2)
            ))
    
    for level, strength in resistance_clusters.items():
        if level > current_price:  # Valid resistance
            distance = ((level - current_price) / current_price) * 100
            resistance_levels.append(SupportResistance(
                level=round(level, 2),
                type="resistance",
                strength=min(strength, 5),
                distance_pct=round(distance, 2)
            ))
    
    # Sort by distance from current price
    support_levels.sort(key=lambda x: x.distance_pct)
    resistance_levels.sort(key=lambda x: x.distance_pct)
    
    return support_levels[:3], resistance_levels[:3]  # Top 3 each


def detect_candlestick_patterns(df: pd.DataFrame) -> List[CandlePattern]:
    """
    Detect key candlestick patterns on the last bar.
    
    Patterns detected:
    - Bullish: Hammer, Bullish Engulfing, Morning Star, Doji at support
    - Bearish: Shooting Star, Bearish Engulfing, Evening Star
    """
    if len(df) < 3:
        return []
    
    patterns = []
    
    # Get last 3 candles
    c0 = df.iloc[-1]  # Current
    c1 = df.iloc[-2]  # Previous
    c2 = df.iloc[-3]  # 2 bars ago
    
    o0, h0, l0, c0_close = c0['Open'], c0['High'], c0['Low'], c0['Close']
    o1, h1, l1, c1_close = c1['Open'], c1['High'], c1['Low'], c1['Close']
    o2, h2, l2, c2_close = c2['Open'], c2['High'], c2['Low'], c2['Close']
    
    body0 = abs(c0_close - o0)
    body1 = abs(c1_close - o1)
    range0 = h0 - l0
    range1 = h1 - l1
    
    # Prevent division by zero
    if range0 == 0:
        range0 = 0.001
    if range1 == 0:
        range1 = 0.001
    
    # === BULLISH PATTERNS ===
    
    # Hammer: Small body at top, long lower shadow
    lower_shadow0 = min(o0, c0_close) - l0
    upper_shadow0 = h0 - max(o0, c0_close)
    
    if (lower_shadow0 > 2 * body0 and 
        upper_shadow0 < body0 * 0.5 and
        body0 / range0 < 0.4):
        patterns.append(CandlePattern("Hammer", "bullish", 2))
    
    # Bullish Engulfing: Current body completely covers previous bearish body
    if (c1_close < o1 and  # Previous was bearish
        c0_close > o0 and  # Current is bullish
        o0 <= c1_close and  # Open below previous close
        c0_close >= o1):  # Close above previous open
        patterns.append(CandlePattern("Bullish Engulfing", "bullish", 3))
    
    # Morning Star: Bearish candle, small body, bullish candle
    if (c2_close < o2 and  # First was bearish
        body1 / range1 < 0.3 and  # Middle is small body (doji-like)
        c0_close > o0 and  # Current is bullish
        c0_close > (o2 + c2_close) / 2):  # Current closes above first midpoint
        patterns.append(CandlePattern("Morning Star", "bullish", 3))
    
    # Bullish Doji (at potential reversal)
    if body0 / range0 < 0.1 and range0 > 0:
        patterns.append(CandlePattern("Doji", "neutral", 1))
    
    # === BEARISH PATTERNS ===
    
    # Shooting Star: Small body at bottom, long upper shadow
    if (upper_shadow0 > 2 * body0 and 
        lower_shadow0 < body0 * 0.5 and
        body0 / range0 < 0.4):
        patterns.append(CandlePattern("Shooting Star", "bearish", 2))
    
    # Bearish Engulfing
    if (c1_close > o1 and  # Previous was bullish
        c0_close < o0 and  # Current is bearish
        o0 >= c1_close and  # Open above previous close
        c0_close <= o1):  # Close below previous open
        patterns.append(CandlePattern("Bearish Engulfing", "bearish", 3))
    
    # Evening Star
    if (c2_close > o2 and  # First was bullish
        body1 / range1 < 0.3 and  # Middle is small body
        c0_close < o0 and  # Current is bearish
        c0_close < (o2 + c2_close) / 2):  # Current closes below first midpoint
        patterns.append(CandlePattern("Evening Star", "bearish", 3))
    
    return patterns


def calculate_relative_strength(
    stock_df: pd.DataFrame,
    benchmark_df: pd.DataFrame,
    period: int = 20,
) -> float:
    """
    Calculate relative strength vs benchmark (NIFTY50).
    
    RS = (Stock % Change) / (Benchmark % Change)
    RS > 1.0 = outperforming, RS < 1.0 = underperforming
    """
    if len(stock_df) < period or len(benchmark_df) < period:
        return 1.0  # Neutral if insufficient data
    
    stock_returns = (stock_df['Close'].iloc[-1] / stock_df['Close'].iloc[-period] - 1) * 100
    bench_returns = (benchmark_df['Close'].iloc[-1] / benchmark_df['Close'].iloc[-period] - 1) * 100
    
    if bench_returns == 0:
        return 1.0
    
    return round(stock_returns / bench_returns, 2) if bench_returns != 0 else 1.0


def detect_pullback_to_ema(
    df: pd.DataFrame,
    ema_col: str = 'EMA20',
    tolerance_pct: float = 1.5,
) -> Tuple[bool, str]:
    """
    Detect if price is pulling back to EMA (good entry opportunity).
    
    Returns:
        (is_pullback, description)
    """
    if ema_col not in df.columns:
        return False, ""
    
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest
    
    price = latest['Close']
    ema = latest[ema_col]
    prev_price = prev['Close']
    prev_ema = prev[ema_col]
    
    distance_pct = abs(price - ema) / ema * 100
    
    # Bullish pullback: Price was above EMA, came back near it, still above
    if (prev_price > prev_ema and 
        price > ema and 
        distance_pct <= tolerance_pct and
        price < prev_price):  # Price declining (pulling back)
        return True, f"Bullish pullback to {ema_col} ({distance_pct:.1f}% away)"
    
    # Bearish pullback: Price was below EMA, bounced up near it, still below
    if (prev_price < prev_ema and 
        price < ema and 
        distance_pct <= tolerance_pct and
        price > prev_price):  # Price rising (pulling back up)
        return True, f"Bearish pullback to {ema_col} ({distance_pct:.1f}% away)"
    
    return False, ""


def calculate_momentum_quality(df: pd.DataFrame) -> Dict[str, any]:
    """
    Calculate comprehensive momentum quality metrics.
    
    Quality factors:
    - Trend consistency (% of green candles)
    - Volume trend (rising/falling)
    - RSI divergence detection
    - MACD momentum
    """
    if len(df) < 20:
        return {"quality": "unknown", "score": 50}
    
    recent = df.tail(20)
    
    # Trend consistency
    green_candles = (recent['Close'] > recent['Open']).sum()
    trend_consistency = green_candles / 20 * 100
    
    # Volume trend
    vol_first_half = recent['Volume'].iloc[:10].mean()
    vol_second_half = recent['Volume'].iloc[10:].mean()
    volume_trend = "rising" if vol_second_half > vol_first_half else "falling"
    
    # RSI divergence (simplified)
    rsi_divergence = "none"
    if 'RSI' in df.columns:
        price_higher = recent['Close'].iloc[-1] > recent['Close'].iloc[-10]
        rsi_higher = recent['RSI'].iloc[-1] > recent['RSI'].iloc[-10]
        
        if price_higher and not rsi_higher:
            rsi_divergence = "bearish"
        elif not price_higher and rsi_higher:
            rsi_divergence = "bullish"
    
    # Calculate quality score
    score = 50
    
    if trend_consistency > 60:
        score += 15
    elif trend_consistency < 40:
        score -= 15
    
    if volume_trend == "rising":
        score += 10
    
    if rsi_divergence == "bearish":
        score -= 20
    elif rsi_divergence == "bullish":
        score += 10
    
    quality = "strong" if score >= 70 else "moderate" if score >= 50 else "weak"
    
    return {
        "quality": quality,
        "score": score,
        "trend_consistency": round(trend_consistency, 1),
        "volume_trend": volume_trend,
        "rsi_divergence": rsi_divergence,
    }


def is_near_support(price: float, support_levels: List[SupportResistance], threshold_pct: float = 2.0) -> bool:
    """Check if price is near a support level"""
    for sr in support_levels:
        if sr.distance_pct <= threshold_pct:
            return True
    return False


def is_near_resistance(price: float, resistance_levels: List[SupportResistance], threshold_pct: float = 2.0) -> bool:
    """Check if price is near a resistance level"""
    for sr in resistance_levels:
        if sr.distance_pct <= threshold_pct:
            return True
    return False


def get_weekly_trend(df_daily: pd.DataFrame) -> str:
    """
    Determine weekly trend from daily data.
    Uses 20-bar EMA on weekly-resampled data.
    """
    if len(df_daily) < 60:  # Need at least 60 days for weekly analysis
        return "neutral"
    
    try:
        # Resample to weekly
        weekly = df_daily.resample('W').agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        }).dropna()
        
        if len(weekly) < 10:
            return "neutral"
        
        weekly['EMA10'] = ta.ema(weekly['Close'], length=10)
        weekly['EMA20'] = ta.ema(weekly['Close'], length=20)
        
        latest = weekly.iloc[-1]
        
        if latest['Close'] > latest['EMA10'] > latest['EMA20']:
            return "bullish"
        elif latest['Close'] < latest['EMA10'] < latest['EMA20']:
            return "bearish"
        else:
            return "neutral"
    except Exception as e:
        logger.warning(f"Weekly trend calculation failed: {e}")
        return "neutral"
