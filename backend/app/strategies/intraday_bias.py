"""
TradeEdge Pro - Intraday Bias Strategy
15m EOD Simulation - NOT live intraday trading
"""
from typing import Optional
import pandas as pd
import pandas_ta as ta

from app.strategies.base import BaseStrategy, Signal
from app.utils.logger import get_logger

logger = get_logger(__name__)


class IntradayBiasStrategy(BaseStrategy):
    """
    - Volume Confirmation > 1.2x 20-bar avg
    """
    
    name = "intraday_bias"
    
    def add_vwap(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add VWAP indicator"""
        df['VWAP'] = ta.vwap(df['High'], df['Low'], df['Close'], df['Volume'])
        return df
    
    def analyze(self, df: pd.DataFrame, symbol: str, sector: str = "") -> Optional[Signal]:
        """Analyze 15m data for intraday bias signal"""
        
        # Validate data
        if not self.validate_data(df):
            return None
        
        # Add indicators
        df = self.add_indicators(df)
        df = self.add_vwap(df)
        
        # Drop NaN rows from indicator calculation
        df = df.dropna()
        if len(df) < 20:
            return None
        
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        # Import sector benchmarks for dynamic ATR caps
        from app.data.sector_benchmarks import get_sector_atr_cap, get_sector_atr_min
        
        atr_pct = latest.get('ATR_PCT', 0)
        atr_min = get_sector_atr_min(sector)
        atr_max = get_sector_atr_cap(sector)
        
        # Filter 1: Volatility check (sector-specific)
        if atr_pct < atr_min:
            logger.debug(f"{symbol}: Volatility too low ({atr_pct:.2f}% < {atr_min}% for {sector or 'DEFAULT'})")
            return None
        if atr_pct > atr_max:
            logger.debug(f"{symbol}: Volatility too high ({atr_pct:.2f}% > {atr_max}% for {sector or 'DEFAULT'})")
            return None
        
        # Filter 2: Volume confirmation (> 1.2x average)
        volume_ratio = latest.get('Volume_Ratio', 0)
        if volume_ratio < 1.2:
            logger.debug(f"{symbol}: Volume too low ({volume_ratio:.2f}x)")
            return None
        
        # Detect EMA crossover
        ema9_cross_up = prev['EMA9'] <= prev['EMA21'] and latest['EMA9'] > latest['EMA21']
        ema9_cross_down = prev['EMA9'] >= prev['EMA21'] and latest['EMA9'] < latest['EMA21']
        
        # VWAP bias
        price = latest['Close']
        vwap = latest.get('VWAP', price)
        above_vwap = price > vwap
        below_vwap = price < vwap
        
        signal_type = None
        
        # BUY Signal: EMA9 crosses above EMA21 + Price > VWAP
        if ema9_cross_up and above_vwap:
            signal_type = "BUY"
        
        # SELL Signal: EMA9 crosses below EMA21 + Price < VWAP
        elif ema9_cross_down and below_vwap:
            signal_type = "SELL"
        
        if not signal_type:
            return None
        
        # Calculate entry, SL, targets
        atr = latest['ATR']
        
        if signal_type == "BUY":
            entry_low = price
            entry_high = price + (atr * 0.3)
            stop_loss = price - (atr * 1.5)
            target1 = price + (atr * 2)
            target2 = price + (atr * 3)
        else:  # SELL
            entry_low = price - (atr * 0.3)
            entry_high = price
            stop_loss = price + (atr * 1.5)
            target1 = price - (atr * 2)
            target2 = price - (atr * 3)
        
        # Calculate R:R
        risk_reward = self.calculate_risk_reward(price, stop_loss, target1)
        
        # Get trend strength
        trend_strength = self.get_trend_strength(df)
        
        # EMA alignment description
        if latest['EMA9'] > latest['EMA21']:
            ema_alignment = "9EMA > 21EMA (Bullish)"
        else:
            ema_alignment = "9EMA < 21EMA (Bearish)"
        
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
            rsi_value=latest.get('RSI', 50),
            adx_value=latest.get('ADX', 0),
            volume_ratio=volume_ratio,
        )
        
        logger.info(f"{symbol}: {signal_type} signal generated (R:R {risk_reward:.1f})")
        return signal
