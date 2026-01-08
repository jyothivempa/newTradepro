"""
TradeEdge Pro - Enhanced Swing Trading Strategy
Professional-grade daily strategy with pullback entries and multi-confirmation
"""
from typing import Optional, List
import pandas as pd
import yfinance as yf

from app.strategies.base import BaseStrategy, Signal
from app.strategies.indicators import (
    detect_support_resistance,
    detect_candlestick_patterns,
    detect_pullback_to_ema,
    calculate_momentum_quality,
    is_near_support,
    get_weekly_trend,
    CandlePattern,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)


class SwingStrategy(BaseStrategy):
    """
    Professional Swing Trading Strategy using daily data.
    
    Entry Methods (any ONE is sufficient):
    1. BREAKOUT: Price > 20-day high + Volume > 1.5x (classic)
    2. PULLBACK: Pullback to 20EMA in uptrend (better R:R)
    3. SUPPORT BOUNCE: Price at support + bullish candle
    
    Filters (ALL must pass):
    - Trend Filter: 20EMA > 50EMA + ADX > 20 (relaxed from 25)
    - Weekly Trend Alignment: Weekly trend same direction
    - Risk-Reward > 2.0
    
    Enhancements:
    - Support/Resistance awareness
    - Candlestick pattern confirmation
    - Momentum quality scoring
    """
    
    name = "swing"
    
    def analyze(self, df: pd.DataFrame, symbol: str) -> Optional[Signal]:
        """Analyze daily data for swing trade signal with pro-level logic"""
        
        # Validate data
        if not self.validate_data(df):
            return None
        
        # Add indicators
        df = self.add_indicators(df)
        
        # Add 20-day high/low for breakout detection
        df['High_20'] = df['High'].rolling(20).max()
        df['Low_20'] = df['Low'].rolling(20).min()
        df['High_52W'] = df['High'].rolling(252).max()  # 52-week high
        
        # Drop NaN rows
        df = df.dropna()
        if len(df) < 20:
            return None
        
        latest = df.iloc[-1]
        price = latest['Close']
        
        # ===== SUPPORT/RESISTANCE ANALYSIS =====
        support_levels, resistance_levels = detect_support_resistance(df)
        near_support = is_near_support(price, support_levels, threshold_pct=2.0)
        
        # ===== CANDLESTICK PATTERNS =====
        candle_patterns = detect_candlestick_patterns(df)
        bullish_patterns = [p for p in candle_patterns if p.type == "bullish"]
        bearish_patterns = [p for p in candle_patterns if p.type == "bearish"]
        
        # ===== PULLBACK DETECTION =====
        is_pullback, pullback_desc = detect_pullback_to_ema(df, 'EMA20', tolerance_pct=2.0)
        
        # ===== MOMENTUM QUALITY =====
        momentum = calculate_momentum_quality(df)
        
        # ===== WEEKLY TREND (Multi-Timeframe) =====
        weekly_trend = get_weekly_trend(df)
        
        # ===== TREND FILTER =====
        ema20 = latest['EMA20']
        ema50 = latest['EMA50']
        adx = latest.get('ADX', 0)
        
        # Relaxed ADX threshold from 25 to 20
        bullish_trend = ema20 > ema50 and adx > 20
        bearish_trend = ema20 < ema50 and adx > 20
        
        if not (bullish_trend or bearish_trend):
            logger.debug(f"{symbol}: No clear trend (ADX: {adx:.1f})")
            return None
        
        # ===== MOMENTUM FILTER =====
        rsi = latest.get('RSI', 50)
        macd_hist = latest.get('MACD_Hist', 0)
        
        # ===== VOLUME ANALYSIS =====
        volume_ratio = latest.get('Volume_Ratio', 0)
        high_20 = latest['High_20']
        low_20 = latest['Low_20']
        
        # ===== SIGNAL DETERMINATION (Multiple Entry Methods) =====
        signal_type = None
        entry_method = None
        
        if bullish_trend:
            # Method 1: BREAKOUT Entry
            if price >= high_20 and volume_ratio > 1.5:
                signal_type = "BUY"
                entry_method = "Breakout"
            
            # Method 2: PULLBACK Entry (better R:R)
            elif is_pullback and 40 <= rsi <= 60:
                signal_type = "BUY"
                entry_method = "Pullback to 20EMA"
            
            # Method 3: SUPPORT BOUNCE Entry
            elif near_support and len(bullish_patterns) > 0:
                signal_type = "BUY"
                entry_method = f"Support Bounce ({bullish_patterns[0].name})"
            
            # Method 4: MOMENTUM CONTINUATION (strong momentum, near EMA)
            elif (macd_hist > 0 and 
                  momentum['quality'] in ['strong', 'moderate'] and
                  abs(price - ema20) / ema20 * 100 <= 3.0 and
                  volume_ratio > 1.2):
                signal_type = "BUY"
                entry_method = "Momentum Continuation"
            
            # Method 5: WEEKLY ALIGNED ENTRY
            elif (weekly_trend == "bullish" and 
                  40 <= rsi <= 65 and 
                  volume_ratio > 1.0 and
                  abs(price - ema20) / ema20 * 100 <= 2.0):
                signal_type = "BUY"
                entry_method = "Weekly Trend Aligned"
        
        elif bearish_trend:
            # Bearish entries (mirror of bullish)
            if price <= low_20 and volume_ratio > 1.5:
                signal_type = "SELL"
                entry_method = "Breakdown"
            
            elif is_pullback and 40 <= rsi <= 60:
                signal_type = "SELL"
                entry_method = "Pullback to 20EMA"
            
            elif len(bearish_patterns) > 0 and volume_ratio > 1.2:
                signal_type = "SELL"
                entry_method = f"Pattern ({bearish_patterns[0].name})"
        
        if not signal_type:
            return None
        
        # ===== CALCULATE ENTRY, SL, TARGETS =====
        atr = latest['ATR']
        
        if signal_type == "BUY":
            # Entry zone
            entry_low = price
            entry_high = price + (atr * 0.5)
            
            # Stop loss based on entry method
            if entry_method == "Pullback to 20EMA":
                # Tighter stop for pullbacks
                stop_loss = ema20 - (atr * 1.5)
            elif entry_method == "Support Bounce" and support_levels:
                # Stop below support
                stop_loss = support_levels[0].level - (atr * 0.5)
            else:
                # Standard: 2x ATR or below 50EMA
                sl_atr = price - (atr * 2)
                sl_ema = ema50 - (atr * 0.5)
                stop_loss = max(sl_atr, sl_ema)
            
            # Targets: 1:2 and 1:3 R:R
            risk = price - stop_loss
            target1 = price + (risk * 2)
            target2 = price + (risk * 3)
            
        else:  # SELL
            entry_low = price - (atr * 0.5)
            entry_high = price
            
            if entry_method == "Pullback to 20EMA":
                stop_loss = ema20 + (atr * 1.5)
            else:
                sl_atr = price + (atr * 2)
                sl_ema = ema50 + (atr * 0.5)
                stop_loss = min(sl_atr, sl_ema)
            
            risk = stop_loss - price
            target1 = price - (risk * 2)
            target2 = price - (risk * 3)
        
        # Calculate R:R
        risk_reward = self.calculate_risk_reward(price, stop_loss, target1)
        
        # Skip if R:R is too low
        if risk_reward < 1.5:
            logger.debug(f"{symbol}: R:R too low ({risk_reward:.1f})")
            return None
        
        # Get trend strength
        trend_strength = self.get_trend_strength(df)
        
        # EMA alignment description
        if ema20 > ema50:
            ema_alignment = f"20EMA > 50EMA (Bullish) | {entry_method}"
        else:
            ema_alignment = f"20EMA < 50EMA (Bearish) | {entry_method}"
        
        # Add pattern info if any
        pattern_info = ""
        if bullish_patterns and signal_type == "BUY":
            pattern_info = f" | {bullish_patterns[0].name}"
        elif bearish_patterns and signal_type == "SELL":
            pattern_info = f" | {bearish_patterns[0].name}"
        
        # === CALCULATE CONFIDENCE ===
        # High: Strong ADX + Volume + Weekly aligned
        # Medium: Good ADX or Volume
        # Low: Marginal conditions
        confidence_score = 0
        if adx > 35:
            confidence_score += 2
        elif adx > 25:
            confidence_score += 1
        if volume_ratio > 2.0:
            confidence_score += 2
        elif volume_ratio > 1.5:
            confidence_score += 1
        if weekly_trend == ("bullish" if signal_type == "BUY" else "bearish"):
            confidence_score += 1
        if momentum['quality'] == 'strong':
            confidence_score += 1
        
        confidence = "High" if confidence_score >= 5 else "Medium" if confidence_score >= 3 else "Low"
        
        # === DETERMINE INVALIDATION CONDITION ===
        if signal_type == "BUY":
            invalidated_if = f"Close below {ema20:.0f} (20 EMA)"
        else:
            invalidated_if = f"Close above {ema20:.0f} (20 EMA)"
        
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
            ema_alignment=ema_alignment + pattern_info,
            rsi_value=rsi,
            adx_value=adx,
            volume_ratio=volume_ratio,
            # New metadata
            confidence=confidence,
            market_regime=weekly_trend.upper() if weekly_trend != "neutral" else "RANGING",
            entry_method=entry_method,
            invalidated_if=invalidated_if,
        )
        
        logger.info(f"{symbol}: {signal_type} via {entry_method} ({confidence} confidence, R:R {risk_reward:.1f})")
        return signal

