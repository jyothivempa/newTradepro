"""
TradeEdge Pro - Enhanced Signal Scorer
Context-aware scoring with breakdown for explainability
"""
from dataclasses import dataclass, field
from typing import Dict, Optional
import pandas as pd

from app.strategies.base import Signal
from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class ScoreBreakdown:
    """Detailed score breakdown for explainability"""
    base_score: int = 100
    deductions: Dict[str, int] = field(default_factory=dict)
    bonuses: Dict[str, int] = field(default_factory=dict)
    final_score: int = 0
    
    def to_dict(self) -> dict:
        return {
            "base": self.base_score,
            "deductions": self.deductions,
            "bonuses": self.bonuses,
            "final": self.final_score,
        }


class SignalScorer:
    """
    Context-aware scoring system with explainable breakdown.
    
    Base Score: 100
    Deductions for weak signals
    Bonuses for strong confirmations
    """
    
    def __init__(self, market_regime: str = "neutral", nifty_trend: str = "neutral"):
        """
        Initialize scorer with market context.
        
        Args:
            market_regime: "bullish", "bearish", "sideways", or "neutral"
            nifty_trend: "bullish" if NIFTY 20EMA > 50EMA, else "bearish"
        """
        self.market_regime = market_regime
        self.nifty_trend = nifty_trend
    
    def calculate_score(self, signal: Signal, extra_context: dict = None) -> tuple[int, ScoreBreakdown]:
        """
        Calculate context-aware score with pro-level breakdown.
        
        Args:
            signal: The trading signal to score
            extra_context: Optional dict with additional context:
                - entry_method: str ("Pullback", "Breakout", etc.)
                - near_support: bool
                - has_bullish_pattern: bool
                - relative_strength: float
                - momentum_quality: str
                - weekly_aligned: bool
        
        Returns:
            (final_score, breakdown)
        """
        breakdown = ScoreBreakdown()
        extra = extra_context or {}
        
        # === DEDUCTIONS ===
        
        # 1. Market Against (Critical)
        if self.nifty_trend == "bearish" and signal.signal_type == "BUY":
            breakdown.deductions["Market Against Trend"] = -25
        elif self.nifty_trend == "bullish" and signal.signal_type == "SELL":
            breakdown.deductions["Market Against Trend"] = -25
        
        # 2. Weak Volume
        if signal.volume_ratio < 1.0:
            breakdown.deductions["Very Weak Volume"] = -25
        elif signal.volume_ratio < 1.2:
            breakdown.deductions["Weak Volume"] = -15
        elif signal.volume_ratio < 1.5:
            breakdown.deductions["Below Avg Volume"] = -5
        
        # 3. Weak Trend
        if signal.trend_strength == "Weak":
            breakdown.deductions["Weak Trend"] = -20
        elif signal.trend_strength == "Moderate":
            breakdown.deductions["Moderate Trend"] = -5
        
        # 4. RSI Extreme Zones (Reversal Risk)
        if signal.rsi_value > 80:
            breakdown.deductions["RSI Overbought Extreme"] = -25
        elif signal.rsi_value > 70:
            breakdown.deductions["RSI Overbought"] = -15
        elif signal.rsi_value < 20:
            breakdown.deductions["RSI Oversold Extreme"] = -25
        elif signal.rsi_value < 30:
            breakdown.deductions["RSI Oversold"] = -15
        
        # 5. Low ADX (No Clear Trend)
        if signal.adx_value < 15:
            breakdown.deductions["ADX Very Low"] = -20
        elif signal.adx_value < 20:
            breakdown.deductions["ADX Low"] = -10
        
        # 6. Poor Risk-Reward
        if signal.risk_reward < 2.0:
            breakdown.deductions["Low R:R"] = -15
        elif signal.risk_reward < 2.5:
            breakdown.deductions["Moderate R:R"] = -5
        
        # 7. Bearish Divergence (from extra context)
        if extra.get('momentum_quality') == 'weak':
            breakdown.deductions["Weak Momentum"] = -10
        
        # === BONUSES ===
        
        # 1. Strong Volume Confirmation
        if signal.volume_ratio > 3.0:
            breakdown.bonuses["Exceptional Volume"] = +20
        elif signal.volume_ratio > 2.5:
            breakdown.bonuses["Strong Volume"] = +15
        elif signal.volume_ratio > 2.0:
            breakdown.bonuses["Good Volume"] = +10
        
        # 2. Strong ADX
        if signal.adx_value > 50:
            breakdown.bonuses["Very Strong Trend (ADX)"] = +15
        elif signal.adx_value > 40:
            breakdown.bonuses["Strong Trend (ADX)"] = +10
        elif signal.adx_value > 30:
            breakdown.bonuses["Good Trend (ADX)"] = +5
        
        # 3. Market Aligned
        if self.nifty_trend == "bullish" and signal.signal_type == "BUY":
            breakdown.bonuses["Market Aligned"] = +10
        elif self.nifty_trend == "bearish" and signal.signal_type == "SELL":
            breakdown.bonuses["Market Aligned"] = +10
        
        # 4. RSI Sweet Spot
        if 45 <= signal.rsi_value <= 55:
            breakdown.bonuses["RSI Perfect Zone"] = +10
        elif 40 <= signal.rsi_value <= 60:
            breakdown.bonuses["RSI Sweet Spot"] = +5
        
        # 5. Excellent R:R
        if signal.risk_reward >= 4.0:
            breakdown.bonuses["Excellent R:R"] = +15
        elif signal.risk_reward >= 3.0:
            breakdown.bonuses["Good R:R"] = +10
        
        # === NEW PRO-LEVEL BONUSES ===
        
        # 6. Pullback Entry (better entries)
        entry_method = extra.get('entry_method', '')
        if 'Pullback' in entry_method:
            breakdown.bonuses["Pullback Entry"] = +15
        
        # 7. Support/Resistance Proximity
        if extra.get('near_support') and signal.signal_type == "BUY":
            breakdown.bonuses["Near Support"] = +10
        if extra.get('near_resistance') and signal.signal_type == "SELL":
            breakdown.bonuses["Near Resistance"] = +10
        
        # 8. Candlestick Pattern Confirmation
        if extra.get('has_bullish_pattern') and signal.signal_type == "BUY":
            breakdown.bonuses["Bullish Pattern"] = +10
        if extra.get('has_bearish_pattern') and signal.signal_type == "SELL":
            breakdown.bonuses["Bearish Pattern"] = +10
        
        # 9. Relative Strength
        rs = extra.get('relative_strength', 1.0)
        if rs > 1.5:
            breakdown.bonuses["Strong Relative Strength"] = +15
        elif rs > 1.2:
            breakdown.bonuses["Good Relative Strength"] = +10
        elif rs < 0.7:
            breakdown.deductions["Weak Relative Strength"] = -10
        
        # 10. Weekly Trend Alignment
        if extra.get('weekly_aligned'):
            breakdown.bonuses["Weekly Trend Aligned"] = +10
        
        # 11. Strong Momentum Quality
        if extra.get('momentum_quality') == 'strong':
            breakdown.bonuses["Strong Momentum"] = +10
        
        # === CALCULATE FINAL WITH CATEGORY CAPS ===
        # Prevent score inflation by capping bonuses per category
        
        BONUS_CAPS = {
            "trend": 25,      # ADX-related bonuses
            "volume": 20,     # Volume-related bonuses
            "pattern": 15,    # Candlestick patterns
            "alignment": 15,  # Market/weekly alignment
            "momentum": 10,   # Momentum quality
            "entry": 15,      # Entry method (pullback, S/R)
            "rr": 15,         # Risk-reward
        }
        
        # Categorize bonuses
        bonus_categories = {
            "trend": ["Very Strong Trend (ADX)", "Strong Trend (ADX)", "Good Trend (ADX)", "Strong Relative Strength", "Good Relative Strength"],
            "volume": ["Exceptional Volume", "Strong Volume", "Good Volume"],
            "pattern": ["Bullish Pattern", "Bearish Pattern"],
            "alignment": ["Market Aligned", "Weekly Trend Aligned"],
            "momentum": ["Strong Momentum", "RSI Perfect Zone", "RSI Sweet Spot"],
            "entry": ["Pullback Entry", "Near Support", "Near Resistance"],
            "rr": ["Excellent R:R", "Good R:R"],
        }
        
        # Apply caps to bonuses
        capped_bonuses = 0
        for category, cap in BONUS_CAPS.items():
            category_bonus = sum(
                breakdown.bonuses.get(name, 0) 
                for name in bonus_categories.get(category, [])
            )
            capped_bonuses += min(category_bonus, cap)
        
        total_deductions = sum(breakdown.deductions.values())
        
        # Store capping info in breakdown
        original_bonus_total = sum(breakdown.bonuses.values())
        if original_bonus_total > capped_bonuses:
            breakdown.bonuses["[CAPPED]"] = capped_bonuses - original_bonus_total
        
        breakdown.final_score = max(0, min(100, 
            breakdown.base_score + total_deductions + capped_bonuses
        ))
        
        # === SOFT CEILING ===
        # Fix for Score Inflation: Reserve 95-100 for exceptional setups
        
        ceiling = 100
        ceiling_reason = ""
        
        # 1. Regime Check: If not TRENDING, cap at 92
        # self.market_regime is set in __init__
        regime = self.market_regime.upper() if self.market_regime else "NEUTRAL"
        
        if regime != "TRENDING":
            if breakdown.final_score > 92:
                ceiling = 92
                ceiling_reason = f"Soft Ceiling ({regime.title()} Market)"
        else:
            # 2. Quality Check (Trending)
            # Reserve > 95 for High Confidence + High R:R
            # We use signal.confidence (str) and signal.risk_reward (float)
            is_high_quality = (signal.confidence == "High" and signal.risk_reward >= 3.0)
            
            if breakdown.final_score > 95 and not is_high_quality:
                ceiling = 95
                ceiling_reason = "Soft Ceiling (Quality Check)"
        
        # Apply Ceiling
        if breakdown.final_score > ceiling:
            diff = breakdown.final_score - ceiling
            breakdown.deductions[ceiling_reason] = -diff
            breakdown.final_score = ceiling
            
        return breakdown.final_score, breakdown
    
    def passes_threshold(self, score: int) -> bool:
        """Check if score passes minimum threshold"""
        return score >= settings.min_signal_score


def get_nifty_trend() -> str:
    """
    Determine NIFTY 50 trend for market regime filter.
    Returns "bullish" if 20EMA > 50EMA, else "bearish"
    """
    try:
        import yfinance as yf
        import pandas_ta as ta
        
        # Fetch NIFTY 50 data
        nifty = yf.download("^NSEI", period="3mo", progress=False)
        if nifty.empty:
            return "neutral"
        
        # Handle MultiIndex columns
        if isinstance(nifty.columns, pd.MultiIndex):
            nifty.columns = nifty.columns.droplevel(1)
        
        # Calculate EMAs
        nifty['EMA20'] = ta.ema(nifty['Close'], length=20)
        nifty['EMA50'] = ta.ema(nifty['Close'], length=50)
        
        latest = nifty.iloc[-1]
        
        if latest['EMA20'] > latest['EMA50']:
            logger.info("NIFTY Trend: BULLISH (20EMA > 50EMA)")
            return "bullish"
        else:
            logger.info("NIFTY Trend: BEARISH (20EMA < 50EMA)")
            return "bearish"
    
    except Exception as e:
        logger.warning(f"Failed to get NIFTY trend: {e}")
        return "neutral"


def score_signal(signal: Signal, market_regime: str = "neutral", nifty_trend: str = None) -> tuple[Signal, ScoreBreakdown]:
    """
    Score a signal with context-aware scoring.
    
    Returns:
        (signal with updated score, breakdown)
    """
    if nifty_trend is None:
        nifty_trend = "neutral"  # Will be set by signal_generator
    
    scorer = SignalScorer(market_regime, nifty_trend)
    score, breakdown = scorer.calculate_score(signal)
    signal.score = score
    
    logger.debug(f"{signal.symbol}: Score = {score} (deductions: {sum(breakdown.deductions.values())}, bonuses: {sum(breakdown.bonuses.values())})")
    
    return signal, breakdown
