"""
TradeEdge Pro - Options Strategy Hints
Provides covered call suggestions for low-volatility regimes.

Note: This module provides HINTS only, not full options trading.
"""
from dataclasses import dataclass
from typing import Optional

from app.strategies.base import Signal
from app.engine.market_regime import MarketRegime, RegimeAnalysis
from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class OptionsHint:
    """Options overlay suggestion for a stock signal"""
    strategy: str  # "covered_call", "cash_secured_put", "none"
    reason: str
    suggested_strike_pct: float  # % OTM for strike price
    suggested_expiry: str  # "weekly", "monthly"
    estimated_premium_pct: float  # Estimated premium as % of stock price
    
    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "reason": self.reason,
            "suggestedStrikePct": self.suggested_strike_pct,
            "suggestedExpiry": self.suggested_expiry,
            "estimatedPremiumPct": self.estimated_premium_pct,
        }


def get_options_hint(
    signal: Signal, 
    regime: RegimeAnalysis
) -> Optional[OptionsHint]:
    """
    Suggest options overlay for low-volatility regimes.
    
    Strategy:
    - BUY signals in RANGING/DEAD markets: Suggest covered call
    - SELL signals (shorts) in RANGING: Could suggest cash-secured put on bounce
    
    Returns:
        OptionsHint if applicable, None otherwise
    """
    if not settings.enable_options_hints:
        return None
    
    # Only for BUY signals (we're buying stock + selling call)
    if signal.signal_type != "BUY":
        return None
    
    # Only in low-volatility regimes
    if regime.regime == MarketRegime.RANGING:
        return OptionsHint(
            strategy="covered_call",
            reason="Low volatility, sideways market - enhance yield with covered call",
            suggested_strike_pct=5.0,  # 5% OTM
            suggested_expiry="monthly",
            estimated_premium_pct=1.5,  # ~1.5% premium for monthly ATM/OTM call
        )
    
    elif regime.regime == MarketRegime.DEAD:
        return OptionsHint(
            strategy="covered_call",
            reason="Dead market with minimal movement - capture theta decay",
            suggested_strike_pct=3.0,  # 3% OTM (closer since low movement)
            suggested_expiry="weekly",
            estimated_premium_pct=0.8,  # Lower premium in dead market
        )
    
    # In trending/volatile markets, options overlay is less useful
    # (we want full upside capture in trending, and premiums are expensive in volatile)
    return None


def get_options_overlay_message(hint: OptionsHint) -> str:
    """Format options hint as user-friendly message"""
    if hint.strategy == "covered_call":
        return (
            f"💡 Options Hint: Consider selling a {hint.suggested_strike_pct:.0f}% OTM "
            f"covered call ({hint.suggested_expiry} expiry). "
            f"Estimated premium: ~{hint.estimated_premium_pct:.1f}% of stock price. "
            f"Reason: {hint.reason}"
        )
    return ""


def calculate_covered_call_strike(
    current_price: float, 
    strike_pct_otm: float
) -> float:
    """
    Calculate strike price for covered call.
    Rounds to nearest ₹5 or ₹10 based on price level.
    """
    raw_strike = current_price * (1 + strike_pct_otm / 100)
    
    # Round to exchange strike intervals
    if raw_strike < 100:
        return round(raw_strike / 2.5) * 2.5
    elif raw_strike < 500:
        return round(raw_strike / 5) * 5
    elif raw_strike < 2000:
        return round(raw_strike / 10) * 10
    else:
        return round(raw_strike / 50) * 50
