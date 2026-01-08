"""
TradeEdge Pro - Portfolio Risk Manager V2.0
Portfolio-level risk controls to prevent catastrophic losses.

Critical Controls:
1. Daily Loss Kill Switch (< -2R → block new signals)
2. Weekly Drawdown Limit (< -6R → block for rest of week)
3. Circuit Breaker (3 consecutive losses → pause trading)
4. Sector Exposure Cap (30% max per sector)
5. Numerical Correlation Gating (>0.8 correlation blocks)
6. Regime-Based Position Scaling
"""
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import date
from enum import Enum

from app.utils.logger import get_logger

logger = get_logger(__name__)


class RiskAction(Enum):
    """Risk control actions"""
    ALLOW = "allow"
    BLOCK = "block"
    TIGHTEN_SL = "tighten_sl"
    FORCE_EXIT = "force_exit"


@dataclass
class PortfolioState:
    """Current portfolio state for risk checks"""
    daily_pnl_r: float = 0.0          # Daily P&L in R-multiples
    weekly_pnl_r: float = 0.0         # Weekly P&L
    consecutive_losses: int = 0        # V2.0: Track consecutive losing trades
    open_trades: List[dict] = field(default_factory=list)
    prev_regime: str = "NEUTRAL"
    current_regime: str = "NEUTRAL"
    total_capital: float = 100000.0   # Default capital base
    date: str = field(default_factory=lambda: date.today().isoformat())
    
    def reset_daily(self):
        """Reset daily counters (call at start of day)"""
        self.daily_pnl_r = 0.0
        self.date = date.today().isoformat()
        # Note: consecutive_losses persists across days
        
    def reset_weekly(self):
        """Reset weekly counters (call at start of week)"""
        self.weekly_pnl_r = 0.0
        self.consecutive_losses = 0  # Reset at week start

class PortfolioRiskManager:
    """
    Portfolio-level risk manager V2.0.
    
    Implements:
    1. Daily loss kill switch (-2R)
    2. Weekly drawdown limit (-6R)
    3. Circuit breaker (3 consecutive losses)
    4. Sector exposure cap (30%)
    5. Numerical correlation gating (>0.8)
    6. Regime-based position scaling
    7. Concentration gating (2 trades/sector/direction)
    """
    
    # Regime multipliers for position sizing
    REGIME_MULTIPLIERS = {
        "TRENDING": 1.0,
        "BULLISH": 1.0,
        "RANGING": 0.6,
        "SIDEWAYS": 0.6,
        "VOLATILE": 0.5,
        "DEAD": 0.0,
        "NEUTRAL": 0.7,
    }
    
    def __init__(
        self,
        daily_loss_limit_r: float = 2.0,
        weekly_loss_limit_r: float = 6.0,
        max_same_sector_direction: int = 2,
        max_sector_exposure_pct: float = 0.30,
        consecutive_loss_limit: int = 3,
        correlation_threshold: float = 0.8,
    ):
        self.daily_loss_limit_r = daily_loss_limit_r
        self.weekly_loss_limit_r = weekly_loss_limit_r
        self.max_same_sector_direction = max_same_sector_direction
        self.max_sector_exposure_pct = max_sector_exposure_pct
        self.consecutive_loss_limit = consecutive_loss_limit
        self.correlation_threshold = correlation_threshold
        self.state = PortfolioState()
        
        # Cache for correlation calculations (expensive)
        self._correlation_cache: Dict[str, float] = {}
    
    def check_all_rules(
        self,
        sector: str,
        direction: str,  # "BUY" or "SELL"
        position_value: float = 0.0,
        symbol: str = "",  # V2.0: For correlation check
    ) -> Tuple[bool, str]:
        """
        Run all portfolio risk checks.
        
        Returns:
            (is_allowed, reason)
        """
        # Rule 1: Daily Loss Kill Switch
        if self._check_daily_loss_kill():
            return False, f"Daily loss limit hit ({self.state.daily_pnl_r:.1f}R)"
            
        # Rule 2: Weekly Drawdown Kill Switch
        if self.state.weekly_pnl_r < -self.weekly_loss_limit_r:
            logger.warning(f"🛑 Weekly drawdown limit hit ({self.state.weekly_pnl_r:.1f}R)")
            return False, f"Weekly drawdown limit hit ({self.state.weekly_pnl_r:.1f}R)"
        
        # Rule 3: Circuit Breaker (V2.0)
        if self._check_circuit_breaker():
            return False, f"Circuit breaker: {self.state.consecutive_losses} consecutive losses"
        
        # Rule 4: Concentration Gate (sector + direction)
        if self._check_concentration_gate(sector, direction):
            return False, f"Max {self.max_same_sector_direction} trades in {sector} {direction}"
        
        # Rule 5: Numerical Correlation Gate (V2.0)
        if symbol and self._check_numerical_correlation(symbol):
            return False, f"High correlation (>{self.correlation_threshold}) with existing positions"
            
        # Rule 6: Total Sector Exposure
        if self._check_sector_exposure(sector, position_value):
            return False, f"Sector exposure limit (> {self.max_sector_exposure_pct:.0%}) for {sector}"
        
        return True, ""
    
    def _check_daily_loss_kill(self) -> bool:
        """Block new signals if daily loss exceeds limit."""
        if self.state.daily_pnl_r < -self.daily_loss_limit_r:
            logger.warning(
                f"🛑 Daily loss kill switch: {self.state.daily_pnl_r:.1f}R "
                f"(limit: -{self.daily_loss_limit_r}R)"
            )
            return True
        return False
    
    def _check_circuit_breaker(self) -> bool:
        """Block trading after N consecutive losses."""
        if self.state.consecutive_losses >= self.consecutive_loss_limit:
            logger.warning(
                f"🔴 Circuit breaker: {self.state.consecutive_losses} consecutive losses "
                f"(limit: {self.consecutive_loss_limit})"
            )
            return True
        return False
    
    def _check_concentration_gate(self, sector: str, direction: str) -> bool:
        """Block if too many trades in same sector + direction."""
        same_trades = [
            t for t in self.state.open_trades
            if t.get("sector") == sector and t.get("direction") == direction
        ]
        
        if len(same_trades) >= self.max_same_sector_direction:
            logger.warning(
                f"⚠️ Concentration gate: {len(same_trades)} trades "
                f"already in {sector} {direction}"
            )
            return True
        return False
    
    def _check_numerical_correlation(self, symbol: str) -> bool:
        """
        Block if new symbol has >0.8 correlation with any open trade.
        Uses 30-day price returns correlation.
        """
        open_symbols = [t['symbol'] for t in self.state.open_trades]
        if not open_symbols:
            return False
        
        # Check cache first
        cache_key = f"{symbol}_{'_'.join(sorted(open_symbols))}"
        if cache_key in self._correlation_cache:
            max_corr = self._correlation_cache[cache_key]
            if max_corr > self.correlation_threshold:
                logger.warning(f"⚠️ Correlation gate: {symbol} has {max_corr:.2f} correlation (cached)")
                return True
            return False
        
        try:
            max_corr = self._calculate_max_correlation(symbol, open_symbols)
            self._correlation_cache[cache_key] = max_corr
            
            if max_corr > self.correlation_threshold:
                logger.warning(f"⚠️ Correlation gate: {symbol} has {max_corr:.2f} correlation")
                return True
        except Exception as e:
            logger.debug(f"Correlation check failed for {symbol}: {e}")
            # On error, allow the trade but log
        
        return False
    
    def _calculate_max_correlation(self, symbol: str, open_symbols: List[str]) -> float:
        """
        Calculate max correlation between new symbol and open positions.
        Returns max absolute correlation value (0-1).
        """
        from app.data.fetch_data import fetch_daily_data
        
        # Fetch new symbol data
        new_df = fetch_daily_data(symbol, period="3mo")
        if new_df is None or len(new_df) < 30:
            return 0.0
        
        new_returns = new_df['Close'].pct_change().dropna()
        max_corr = 0.0
        
        for existing in open_symbols:
            existing_df = fetch_daily_data(existing, period="3mo")
            if existing_df is None or len(existing_df) < 30:
                continue
            
            existing_returns = existing_df['Close'].pct_change().dropna()
            
            # Align dates and calculate correlation
            aligned = pd.concat([new_returns, existing_returns], axis=1).dropna()
            if len(aligned) > 20:
                corr = aligned.corr().iloc[0, 1]
                max_corr = max(max_corr, abs(corr))
        
        return max_corr
        
    def _check_sector_exposure(self, sector: str, new_position_value: float) -> bool:
        """Block if total sector exposure > 30% of capital."""
        current_sector_value = sum(
            t.get("value", 0) for t in self.state.open_trades 
            if t.get("sector") == sector
        )
        total_exposure = current_sector_value + new_position_value
        limit = self.state.total_capital * self.max_sector_exposure_pct
        
        if total_exposure > limit:
            logger.warning(f"⚠️ Sector limit: {total_exposure} > {limit} ({sector})")
            return True
        return False
    
    def check_regime_transition(
        self,
        prev_regime: str,
        current_regime: str
    ) -> Optional[RiskAction]:
        """
        Check if regime transition requires action.
        
        Returns:
            RiskAction if action needed, None otherwise
        """
        self.state.prev_regime = prev_regime
        self.state.current_regime = current_regime
        
        # TRENDING → RANGING: Tighten stops
        if prev_regime == "TRENDING" and current_regime in ("RANGING", "DEAD", "SIDEWAYS"):
            logger.warning(f"📉 Regime transition: {prev_regime} → {current_regime}")
            return RiskAction.TIGHTEN_SL
        
        # RANGING → VOLATILE: Consider exit
        if prev_regime == "RANGING" and current_regime == "VOLATILE":
            logger.warning(f"⚠️ Regime transition to VOLATILE")
            return RiskAction.TIGHTEN_SL
        
        return None
    
    def record_trade_result(self, pnl_r: float):
        """Record a trade result in R-multiples"""
        self.state.daily_pnl_r += pnl_r
        self.state.weekly_pnl_r += pnl_r
        
        # Track consecutive losses for circuit breaker
        if pnl_r < 0:
            self.state.consecutive_losses += 1
            logger.debug(f"Loss recorded. Consecutive losses: {self.state.consecutive_losses}")
        else:
            self.state.consecutive_losses = 0  # Reset on win
            logger.debug("Win recorded. Consecutive losses reset.")
        
        logger.debug(f"P&L updated: Daily {self.state.daily_pnl_r:.1f}R, Weekly {self.state.weekly_pnl_r:.1f}R")
    
    def get_regime_multiplier(self, regime: str) -> float:
        """
        Get position size multiplier based on market regime.
        
        Returns:
            Multiplier (0.0 to 1.0) for position scaling
        """
        return self.REGIME_MULTIPLIERS.get(regime.upper(), 0.7)
    
    def reset_circuit_breaker(self):
        """Manually reset circuit breaker (use after review)"""
        self.state.consecutive_losses = 0
        logger.info("🟢 Circuit breaker manually reset")
    
    def clear_correlation_cache(self):
        """Clear correlation cache (call daily)"""
        self._correlation_cache.clear()
        logger.debug("Correlation cache cleared")
    
    def add_open_trade(self, symbol: str, sector: str, direction: str, value: float = 0.0):
        """Track a new open trade"""
        self.state.open_trades.append({
            "symbol": symbol,
            "sector": sector,
            "direction": direction,
            "value": value,
        })
    
    def remove_trade(self, symbol: str):
        """Remove a closed trade"""
        self.state.open_trades = [
            t for t in self.state.open_trades
            if t.get("symbol") != symbol
        ]
    
    def get_status(self) -> dict:
        """Get current portfolio risk status"""
        return {
            "dailyPnlR": round(self.state.daily_pnl_r, 2),
            "weeklyPnlR": round(self.state.weekly_pnl_r, 2),
            "consecutiveLosses": self.state.consecutive_losses,
            "dailyLossLimitR": self.daily_loss_limit_r,
            "weeklyLossLimitR": self.weekly_loss_limit_r,
            "consecutiveLossLimit": self.consecutive_loss_limit,
            "correlationThreshold": self.correlation_threshold,
            "isKillSwitchActive": self._check_daily_loss_kill() or (self.state.weekly_pnl_r < -self.weekly_loss_limit_r),
            "isCircuitBreakerActive": self._check_circuit_breaker(),
            "openTradeCount": len(self.state.open_trades),
            "currentRegime": self.state.current_regime,
            "regimeMultiplier": self.get_regime_multiplier(self.state.current_regime),
            "sectorConcentration": self._get_sector_concentration(),
        }
    
    def _get_sector_concentration(self) -> Dict[str, int]:
        """Get trade count by sector"""
        concentration = {}
        for trade in self.state.open_trades:
            sector = trade.get("sector", "Unknown")
            concentration[sector] = concentration.get(sector, 0) + 1
        return concentration


# Global instance
portfolio_risk = PortfolioRiskManager()
