"""
TradeEdge Pro - Intraday Bias Engine
Directional bias for next session - NOT a trading strategy.

⚠️ IMPORTANT: This is a DIRECTIONAL BIAS indicator only.
- Does NOT provide entry/exit prices
- Does NOT attach P&L expectations
- Valid for: next session open directional bias
"""
from dataclasses import dataclass
from typing import Optional, List
import pandas as pd
import pandas_ta as ta

from app.strategies.base import BaseStrategy
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class IntradayBias:
    """
    Directional bias output (NOT a trading signal).
    
    This indicates likely direction for next session,
    but should NOT be used for P&L calculations.
    """
    symbol: str
    bias: str               # "BULLISH", "BEARISH", "NEUTRAL"
    confidence: float       # 0.0 to 1.0
    valid_for: str          # e.g., "next_session_open"
    reasoning: List[str]    # Why this bias was determined
    atr_pct: float          # Volatility context
    volume_ratio: float     # Volume context
    
    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "bias": self.bias,
            "confidence": round(self.confidence, 2),
            "validFor": self.valid_for,
            "reasoning": self.reasoning,
            "atrPct": round(self.atr_pct, 2),
            "volumeRatio": round(self.volume_ratio, 2),
            # Explicit disclaimers
            "disclaimer": "Directional bias only. Not a trading signal.",
            "noPnlExpectation": True,
        }


class IntradayBiasEngine(BaseStrategy):
    """
    Intraday Bias Engine - Directional indicator only.
    
    ⚠️ This does NOT simulate intraday trading.
    ⚠️ Output is bias/confidence, NOT entry/exit prices.
    ⚠️ No P&L should be attached to this output.
    
    Purpose: Provide directional lean for next session using EOD data.
    """
    
    name = "intraday_bias_engine"
    
    def add_vwap(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add VWAP indicator"""
        df['VWAP'] = ta.vwap(df['High'], df['Low'], df['Close'], df['Volume'])
        return df
    
    def analyze(self, df: pd.DataFrame, symbol: str, sector: str = "") -> Optional[IntradayBias]:
        """
        Analyze data for directional bias.
        
        Returns:
            IntradayBias with direction and confidence (NOT entry/exit)
        """
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
        
        # Get volatility context
        from app.data.sector_benchmarks import get_sector_atr_cap, get_sector_atr_min
        
        atr_pct = latest.get('ATR_PCT', 0)
        atr_min = get_sector_atr_min(sector)
        atr_max = get_sector_atr_cap(sector)
        
        # Filter: Skip if volatility out of range
        if atr_pct < atr_min or atr_pct > atr_max:
            return None
        
        volume_ratio = latest.get('Volume_Ratio', 0)
        
        # === BIAS CALCULATION ===
        reasoning = []
        bullish_score = 0
        bearish_score = 0
        
        # 1. EMA Crossover
        ema9_above = latest['EMA9'] > latest['EMA21']
        ema9_cross_up = prev['EMA9'] <= prev['EMA21'] and ema9_above
        ema9_cross_down = prev['EMA9'] >= prev['EMA21'] and not ema9_above
        
        if ema9_cross_up:
            bullish_score += 2
            reasoning.append("EMA9 crossed above EMA21")
        elif ema9_above:
            bullish_score += 1
            reasoning.append("EMA9 > EMA21")
        elif ema9_cross_down:
            bearish_score += 2
            reasoning.append("EMA9 crossed below EMA21")
        else:
            bearish_score += 1
            reasoning.append("EMA9 < EMA21")
        
        # 2. VWAP Position
        price = latest['Close']
        vwap = latest.get('VWAP', price)
        
        if price > vwap * 1.005:  # Above VWAP by 0.5%
            bullish_score += 1
            reasoning.append("Price above VWAP")
        elif price < vwap * 0.995:  # Below VWAP by 0.5%
            bearish_score += 1
            reasoning.append("Price below VWAP")
        
        # 3. RSI Momentum
        rsi = latest.get('RSI', 50)
        if rsi > 55:
            bullish_score += 1
            reasoning.append(f"RSI bullish ({rsi:.0f})")
        elif rsi < 45:
            bearish_score += 1
            reasoning.append(f"RSI bearish ({rsi:.0f})")
        
        # 4. Volume Confirmation
        if volume_ratio > 1.3:
            # Volume amplifies the bias
            if bullish_score > bearish_score:
                bullish_score += 1
                reasoning.append(f"Volume confirms ({volume_ratio:.1f}x)")
            elif bearish_score > bullish_score:
                bearish_score += 1
                reasoning.append(f"Volume confirms ({volume_ratio:.1f}x)")
        
        # === DETERMINE BIAS ===
        total_score = bullish_score + bearish_score
        
        if bullish_score > bearish_score + 1:
            bias = "BULLISH"
            confidence = min(0.95, 0.5 + (bullish_score - bearish_score) * 0.1)
        elif bearish_score > bullish_score + 1:
            bias = "BEARISH"
            confidence = min(0.95, 0.5 + (bearish_score - bullish_score) * 0.1)
        else:
            bias = "NEUTRAL"
            confidence = 0.4  # Low confidence when unclear
            reasoning.append("Mixed signals")
        
        logger.info(f"{symbol}: Bias {bias} (confidence: {confidence:.0%})")
        
        return IntradayBias(
            symbol=symbol,
            bias=bias,
            confidence=confidence,
            valid_for="next_session_open",
            reasoning=reasoning,
            atr_pct=atr_pct,
            volume_ratio=volume_ratio,
        )


# Keep old class name for backwards compatibility
IntradayBiasStrategy = IntradayBiasEngine
