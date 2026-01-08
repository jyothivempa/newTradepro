"""
TradeEdge Pro - Enhanced Risk Manager
Position sizing, daily risk cap, and sector exposure limits
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import date

from app.strategies.base import Signal
from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class PositionSize:
    """Position sizing result"""
    shares: int
    position_value: float
    risk_amount: float
    risk_percent: float
    valid: bool
    rejection_reason: str = ""


@dataclass 
class RiskSnapshot:
    """Current risk exposure snapshot"""
    capital: float
    risk_per_trade: float
    open_trades: int
    max_trades: int
    risk_used_today: float
    max_daily_risk: float
    sector_exposure: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "capital": self.capital,
            "riskPerTrade": self.risk_per_trade,
            "openTrades": self.open_trades,
            "maxTrades": self.max_trades,
            "riskUsedToday": round(self.risk_used_today, 2),
            "maxDailyRisk": self.max_daily_risk,
            "sectorExposure": self.sector_exposure,
        }


class RiskManager:
    """
    Enhanced risk manager with:
    - Hard kill rules (RR, SL%, max trades)
    - Daily risk cap
    - Sector exposure limits
    """
    
    MAX_SECTOR_EXPOSURE = 30.0  # 30% max per sector
    MAX_DAILY_RISK = 2.0  # 2% daily risk cap
    
    def __init__(
        self,
        capital: float = 100000,
        risk_per_trade: float = 1.0,
        max_open_trades: int = None,
    ):
        self.capital = capital
        self.risk_per_trade = risk_per_trade
        self.max_open_trades = max_open_trades or settings.max_open_trades
        
        # Tracking
        self.open_trades: List[dict] = []  # {symbol, sector, risk_amount}
        self.daily_risk_used: float = 0.0
        self.last_reset_date: date = date.today()
    
    def _reset_daily_if_needed(self):
        """Reset daily risk counter at start of new day"""
        if date.today() != self.last_reset_date:
            self.daily_risk_used = 0.0
            self.last_reset_date = date.today()
            logger.info("Daily risk counter reset")
    
    def get_sector_exposure(self, sector: str) -> float:
        """Get current exposure to a sector as percentage"""
        sector_value = sum(
            t.get('position_value', 0) 
            for t in self.open_trades 
            if t.get('sector', '').lower() == sector.lower()
        )
        return (sector_value / self.capital) * 100 if self.capital > 0 else 0
    
    def validate_signal(self, signal: Signal, sector: str = "") -> tuple[bool, str]:
        """
        Validate signal against all risk rules.
        
        Hard Kills:
        1. RR < 2.0
        2. SL > 5%
        3. Max trades reached
        4. Daily risk cap exceeded
        5. Sector exposure > 30%
        """
        self._reset_daily_if_needed()
        
        # Hard Kill 1: Risk-Reward < 2.0
        if signal.risk_reward < settings.min_risk_reward:
            reason = f"R:R too low ({signal.risk_reward:.1f} < {settings.min_risk_reward})"
            logger.warning(f"{signal.symbol}: REJECTED - {reason}")
            return False, reason
        
        # Hard Kill 2: Stop Loss > 5%
        entry = (signal.entry_low + signal.entry_high) / 2
        sl_distance = abs(entry - signal.stop_loss)
        sl_pct = (sl_distance / entry) * 100
        
        if sl_pct > settings.max_stop_loss_pct:
            reason = f"SL too wide ({sl_pct:.1f}% > {settings.max_stop_loss_pct}%)"
            logger.warning(f"{signal.symbol}: REJECTED - {reason}")
            return False, reason
        
        # Hard Kill 3: Max open trades
        if len(self.open_trades) >= self.max_open_trades:
            reason = f"Max trades ({self.max_open_trades}) reached"
            logger.warning(f"{signal.symbol}: REJECTED - {reason}")
            return False, reason
        
        # Hard Kill 4: Daily risk cap
        trade_risk = self.risk_per_trade
        if self.daily_risk_used + trade_risk > self.MAX_DAILY_RISK:
            reason = f"Daily risk cap exceeded ({self.daily_risk_used:.1f}% + {trade_risk}% > {self.MAX_DAILY_RISK}%)"
            logger.warning(f"{signal.symbol}: REJECTED - {reason}")
            return False, reason
        
        # Hard Kill 5: Sector exposure
        if sector:
            current_sector_exposure = self.get_sector_exposure(sector)
            # Estimate new exposure
            risk_amount = self.capital * (self.risk_per_trade / 100)
            new_position_value = risk_amount / (sl_pct / 100) if sl_pct > 0 else 0
            new_sector_pct = ((current_sector_exposure * self.capital / 100) + new_position_value) / self.capital * 100
            
            if new_sector_pct > self.MAX_SECTOR_EXPOSURE:
                reason = f"Sector exposure too high ({sector}: {new_sector_pct:.0f}% > {self.MAX_SECTOR_EXPOSURE}%)"
                logger.warning(f"{signal.symbol}: REJECTED - {reason}")
                return False, reason
        
        return True, ""

    def check_circuit_breaker(self, nifty_change_pct: float, signal_type: str = "BUY") -> tuple[bool, str]:
        """
        Market Circuit Breaker.
        Block Long trades if NIFTY is down significantly (> 1.5%).
        """
        # Only block BUY signals in crash mode
        if signal_type == "BUY" and nifty_change_pct < -1.5:
            reason = f"Circuit Breaker Active (NIFTY {nifty_change_pct:.2f}% < -1.5%)"
            logger.warning(f"CIRCUIT BREAKER: Blocking Long Signal due to Market Crash")
            return False, reason
            
        return True, ""
    
    def calculate_position_size(
        self,
        signal: Signal,
        sector: str = "",
        capital: float = None,
        risk_pct: float = None,
    ) -> PositionSize:
        """
        Calculate position size with all validations.
        
        Formula: Position Size = (Capital × AdjustedRisk%) / (Entry - SL)
        
        Regime Multipliers:
        - TRENDING: 1.0x
        - RANGING: 0.6x (Reduce risk in chopped markets)
        - VOLATILE: 0.5x (Half risk in high vol)
        """
        cap = capital or self.capital
        base_risk = risk_pct or self.risk_per_trade
        
        # Apply Regime Multiplier
        multiplier = 1.0
        regime = (signal.market_regime or "NEUTRAL").upper()
        
        if "TRENDING" in regime or "BULLISH" in regime:
            multiplier = 1.0
        elif "RANGING" in regime or "SIDEWAYS" in regime:
            multiplier = 0.6
        elif "VOLATILE" in regime:
            multiplier = 0.5
        else:
            multiplier = 0.8 # Default defensive
            
        adjusted_risk_pct = base_risk * multiplier
        
        # Validate first (using base rules? No, use rules as is)
        is_valid, reason = self.validate_signal(signal, sector)
        if not is_valid:
            return PositionSize(
                shares=0,
                position_value=0,
                risk_amount=0,
                risk_percent=0,
                valid=False,
                rejection_reason=reason,
            )
        
        # Calculate amount
        risk_amount = cap * (adjusted_risk_pct / 100)
        entry = (signal.entry_low + signal.entry_high) / 2
        sl_distance = abs(entry - signal.stop_loss)
        
        if sl_distance == 0:
            return PositionSize(
                shares=0,
                position_value=0,
                risk_amount=0,
                risk_percent=0,
                valid=False,
                rejection_reason="Invalid SL (equals entry)",
            )
        
        shares = int(risk_amount / sl_distance)
        position_value = shares * entry
        
        return PositionSize(
            shares=shares,
            position_value=round(position_value, 2),
            risk_amount=round(risk_amount, 2),
            risk_percent=round(adjusted_risk_pct, 2),
            valid=True,
        )
    
    def add_trade(self, symbol: str, sector: str = "", position_value: float = 0):
        """Record a new trade"""
        self._reset_daily_if_needed()
        
        if not any(t['symbol'] == symbol for t in self.open_trades):
            self.open_trades.append({
                'symbol': symbol,
                'sector': sector,
                'position_value': position_value,
            })
            self.daily_risk_used += self.risk_per_trade
            logger.info(f"Trade added: {symbol} | Daily risk: {self.daily_risk_used:.1f}%")
    
    def remove_trade(self, symbol: str):
        """Remove a closed trade"""
        self.open_trades = [t for t in self.open_trades if t['symbol'] != symbol]
        logger.info(f"Trade removed: {symbol}")
    
    def get_snapshot(self) -> RiskSnapshot:
        """Get current risk exposure snapshot"""
        self._reset_daily_if_needed()
        
        # Calculate sector exposure
        sectors = {}
        for t in self.open_trades:
            sector = t.get('sector', 'Unknown')
            if sector not in sectors:
                sectors[sector] = 0
            sectors[sector] += t.get('position_value', 0)
        
        sector_pcts = {
            s: round((v / self.capital) * 100, 1) 
            for s, v in sectors.items()
        }
        
        return RiskSnapshot(
            capital=self.capital,
            risk_per_trade=self.risk_per_trade,
            open_trades=len(self.open_trades),
            max_trades=self.max_open_trades,
            risk_used_today=self.daily_risk_used,
            max_daily_risk=self.MAX_DAILY_RISK,
            sector_exposure=sector_pcts,
        )
    
    def can_take_trade(self) -> bool:
        """Quick check if new trade is allowed"""
        self._reset_daily_if_needed()
        return (
            len(self.open_trades) < self.max_open_trades and
            self.daily_risk_used + self.risk_per_trade <= self.MAX_DAILY_RISK
        )


# Global instance
risk_manager = RiskManager()
