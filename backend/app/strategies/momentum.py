"""
TradeEdge Pro - Momentum Strategy
Institutional-style momentum trading for breakout stocks
"""
from typing import Optional, List
import pandas as pd

from app.strategies.base import BaseStrategy, Signal
from app.strategies.indicators import (
    detect_support_resistance,
    calculate_momentum_quality,
    get_weekly_trend,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)


class MomentumStrategy(BaseStrategy):
    """
    Institutional Momentum Strategy for strong breakout stocks.
    
    Entry Criteria:
    1. Price breaking 52-week high (or within 5%)
    2. Price > 200 SMA (long-term uptrend)
    3. ADX > 25 (strong trend)
    4. Volume > 2x average (institutional accumulation)
    5. Weekly trend bullish
    
    This strategy focuses on catching big moves early.
    Higher risk, higher reward potential.
    """
    
    name = "momentum"
    
    def analyze(self, df: pd.DataFrame, symbol: str) -> Optional[Signal]:
        """Analyze for momentum breakout signal"""
        
        # Validate data
        if not self.validate_data(df):
            return None
        
        # Need at least 200 bars for 200 SMA
        if len(df) < 200:
            return None
        
        # Add indicators
        df = self.add_indicators(df)
        
        # Add 200 SMA for long-term trend
        df['SMA200'] = df['Close'].rolling(200).mean()
        
        # Add 52-week high
        df['High_52W'] = df['High'].rolling(252).max()
        df['High_3M'] = df['High'].rolling(63).max()  # 3-month high
        
        # Drop NaN rows
        df = df.dropna()
        if len(df) < 20:
            return None
        
        latest = df.iloc[-1]
        price = latest['Close']
        
        # ===== TREND FILTERS =====
        sma200 = latest['SMA200']
        ema20 = latest['EMA20']
        ema50 = latest['EMA50']
        adx = latest.get('ADX', 0)
        
        # Long-term uptrend: Price > 200 SMA
        long_term_bullish = price > sma200
        
        # Short-term strength: 20 EMA > 50 EMA
        short_term_bullish = ema20 > ema50
        
        # Strong trend
        strong_trend = adx > 25
        
        if not (long_term_bullish and short_term_bullish and strong_trend):
            return None
        
        # ===== BREAKOUT DETECTION =====
        high_52w = latest['High_52W']
        high_3m = latest['High_3M']
        volume_ratio = latest.get('Volume_Ratio', 0)
        
        # 52-week high breakout (within 3%)
        near_52w_high = price >= high_52w * 0.97
        
        # 3-month high breakout (within 2%)
        near_3m_high = price >= high_3m * 0.98
        
        # Volume confirmation (need 1.8x+ for momentum)
        strong_volume = volume_ratio > 1.8
        
        # ===== SIGNAL DETERMINATION =====
        signal_type = None
        entry_method = None
        
        # Primary: 52-week high breakout with volume
        if near_52w_high and strong_volume:
            signal_type = "BUY"
            entry_method = "52-Week High Breakout"
        
        # Secondary: 3-month high with very strong volume
        elif near_3m_high and volume_ratio > 2.5:
            signal_type = "BUY"
            entry_method = "3-Month High Breakout"
        
        if not signal_type:
            return None
        
        # ===== MOMENTUM QUALITY CHECK =====
        momentum = calculate_momentum_quality(df)
        if momentum['quality'] == 'weak':
            logger.debug(f"{symbol}: Weak momentum quality")
            return None
        
        # ===== WEEKLY TREND CHECK =====
        weekly_trend = get_weekly_trend(df)
        if weekly_trend != "bullish":
            logger.debug(f"{symbol}: Weekly trend not bullish")
            return None
        
        # ===== CALCULATE ENTRY, SL, TARGETS =====
        atr = latest['ATR']
        rsi = latest.get('RSI', 50)
        
        # Entry zone (chase breakout slightly)
        entry_low = price
        entry_high = price + (atr * 0.3)
        
        # Stop loss: Below 20 EMA or 2x ATR (whichever is tighter)
        sl_ema = ema20 - (atr * 0.5)
        sl_atr = price - (atr * 2.5)
        stop_loss = max(sl_ema, sl_atr)
        
        # Targets: Aggressive momentum targets
        risk = price - stop_loss
        target1 = price + (risk * 2.5)  # 1:2.5 R:R
        target2 = price + (risk * 4)    # 1:4 R:R
        
        # Calculate R:R
        risk_reward = self.calculate_risk_reward(price, stop_loss, target1)
        
        if risk_reward < 2.0:
            return None
        
        # Trend strength enhanced for momentum
        trend_strength = "Strong" if adx > 35 else "Moderate"
        
        # EMA alignment description
        distance_from_52w = ((price / high_52w) - 1) * 100
        ema_alignment = f"{entry_method} | {distance_from_52w:.1f}% from 52W High"
        
        signal = Signal(
            symbol=symbol,
            signal_type=signal_type,
            strategy=self.name,
            entry_low=round(entry_low, 2),
            entry_high=round(entry_high, 2),
            stop_loss=round(stop_loss, 2),
            targets=[round(target1, 2), round(target2, 2)],
            trend_strength=trend_strength,
            risk_reward=risk_reward,
            ema_alignment=ema_alignment,
            rsi_value=rsi,
            adx_value=adx,
            volume_ratio=volume_ratio,
        )
        
        logger.info(f"{symbol}: MOMENTUM {signal_type} via {entry_method} (R:R {risk_reward:.1f})")
        return signal
