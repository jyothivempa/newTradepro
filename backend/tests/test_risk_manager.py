"""
TradeEdge Pro - Unit Tests for Risk Manager
"""
import pytest
from datetime import date

# Add backend to path for imports
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.engine.risk_manager import RiskManager
from app.strategies.base import Signal


def create_test_signal(
    symbol: str = "TESTSTOCK",
    entry: float = 100.0,
    stop_loss: float = 95.0,
    target: float = 115.0,
    risk_reward: float = 3.0,
) -> Signal:
    """Create a test signal"""
    return Signal(
        symbol=symbol,
        signal_type="BUY",
        strategy="swing",
        entry_low=entry - 1,
        entry_high=entry + 1,
        stop_loss=stop_loss,
        targets=[target, target * 1.1],
        risk_reward=risk_reward,
    )


class TestRiskManagerValidation:
    """Tests for signal validation"""
    
    def test_valid_signal_passes(self):
        """Test that valid signal passes validation"""
        rm = RiskManager()
        signal = create_test_signal(risk_reward=2.5)
        
        is_valid, reason = rm.validate_signal(signal)
        assert is_valid is True
        assert reason == ""
    
    def test_low_risk_reward_rejected(self):
        """Test that low R:R signal is rejected"""
        rm = RiskManager()
        signal = create_test_signal(risk_reward=1.5)  # Below 2.0
        
        is_valid, reason = rm.validate_signal(signal)
        assert is_valid is False
        assert "R:R too low" in reason
    
    def test_wide_stop_loss_rejected(self):
        """Test that wide SL signal is rejected"""
        rm = RiskManager()
        signal = create_test_signal(
            entry=100.0,
            stop_loss=90.0,  # 10% SL, above 5% limit
            risk_reward=2.5,
        )
        
        is_valid, reason = rm.validate_signal(signal)
        assert is_valid is False
        assert "SL too wide" in reason
    
    def test_max_trades_limit(self):
        """Test that max trades limit is enforced"""
        rm = RiskManager(max_open_trades=2)
        
        # Add 2 trades
        rm.add_trade("STOCK1")
        rm.add_trade("STOCK2")
        
        signal = create_test_signal()
        is_valid, reason = rm.validate_signal(signal)
        
        assert is_valid is False
        assert "Max trades" in reason


class TestPositionSizing:
    """Tests for position sizing calculations"""
    
    def test_position_size_calculation(self):
        """Test position size is calculated correctly"""
        rm = RiskManager(capital=100000, risk_per_trade=1.0)
        signal = create_test_signal(
            entry=100.0,
            stop_loss=95.0,  # 5% SL distance
            risk_reward=2.5,
        )
        
        result = rm.calculate_position_size(signal)
        
        # Risk = 1% of 100000 = 1000
        # Entry = (99 + 101) / 2 = 100
        # SL distance = 100 - 95 = 5
        # Shares = 1000 / 5 = 200
        assert result.shares == 200
        assert result.risk_amount == 1000.0
        assert result.valid is True
    
    def test_invalid_signal_rejected(self):
        """Test that invalid signal is rejected in position sizing"""
        rm = RiskManager()
        signal = create_test_signal(risk_reward=1.0)  # Below threshold
        
        result = rm.calculate_position_size(signal)
        assert result.valid is False
        assert result.shares == 0


class TestDailyRiskCap:
    """Tests for daily risk cap"""
    
    def test_daily_risk_cap_enforced(self):
        """Test that 2% daily risk cap is enforced"""
        rm = RiskManager(risk_per_trade=1.0)
        rm.MAX_DAILY_RISK = 2.0
        
        # Add 2 trades (uses 2% risk)
        rm.add_trade("STOCK1")
        rm.add_trade("STOCK2")
        
        signal = create_test_signal()
        is_valid, reason = rm.validate_signal(signal)
        
        assert is_valid is False
        assert "Daily risk cap" in reason
    
    def test_daily_risk_resets(self):
        """Test that daily risk resets on new day"""
        rm = RiskManager(risk_per_trade=1.0)
        rm.daily_risk_used = 2.0
        
        # Simulate new day
        rm.last_reset_date = date(2020, 1, 1)
        rm._reset_daily_if_needed()
        
        assert rm.daily_risk_used == 0.0


class TestSectorExposure:
    """Tests for sector exposure limits"""
    
    def test_sector_exposure_tracked(self):
        """Test that sector exposure is tracked"""
        rm = RiskManager(capital=100000)
        rm.add_trade("STOCK1", sector="IT", position_value=20000)
        rm.add_trade("STOCK2", sector="IT", position_value=15000)
        
        exposure = rm.get_sector_exposure("IT")
        assert exposure == 35.0  # (20000 + 15000) / 100000 * 100


class TestRiskSnapshot:
    """Tests for risk snapshot"""
    
    def test_snapshot_has_required_fields(self):
        """Test that snapshot contains all required fields"""
        rm = RiskManager()
        snapshot = rm.get_snapshot()
        
        assert hasattr(snapshot, "capital")
        assert hasattr(snapshot, "risk_per_trade")
        assert hasattr(snapshot, "open_trades")
        assert hasattr(snapshot, "max_trades")
        assert hasattr(snapshot, "risk_used_today")
        assert hasattr(snapshot, "max_daily_risk")
        assert hasattr(snapshot, "sector_exposure")


class TestTradeTracking:
    """Tests for trade tracking"""
    
    def test_add_trade(self):
        """Test adding a trade"""
        rm = RiskManager()
        rm.add_trade("TESTSTOCK", sector="IT")
        
        assert len(rm.open_trades) == 1
        assert rm.open_trades[0]["symbol"] == "TESTSTOCK"
    
    def test_remove_trade(self):
        """Test removing a trade"""
        rm = RiskManager()
        rm.add_trade("TESTSTOCK", sector="IT")
        rm.remove_trade("TESTSTOCK")
        
        assert len(rm.open_trades) == 0
    
    def test_can_take_trade(self):
        """Test can_take_trade helper"""
        rm = RiskManager(max_open_trades=5)
        
        assert rm.can_take_trade() is True
        
        # Fill up trades
        for i in range(5):
            rm.add_trade(f"STOCK{i}")
        
        assert rm.can_take_trade() is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
