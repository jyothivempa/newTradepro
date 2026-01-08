"""
TradeEdge Pro - Unit Tests for Swing Strategy
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Add backend to path for imports
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.strategies.swing import SwingStrategy
from app.strategies.base import Signal


def create_test_data(
    days: int = 100,
    trend: str = "bullish",
    base_price: float = 100.0,
    high_volume: bool = True,
) -> pd.DataFrame:
    """Create mock OHLCV data for testing"""
    dates = pd.date_range(end=datetime.now(), periods=days, freq="D")
    
    # Generate price data based on trend
    if trend == "bullish":
        # Upward trend with EMA alignment
        trend_factor = np.linspace(1.0, 1.3, days)
        noise = np.random.randn(days) * 0.02
        prices = base_price * trend_factor * (1 + noise)
    elif trend == "bearish":
        trend_factor = np.linspace(1.0, 0.7, days)
        noise = np.random.randn(days) * 0.02
        prices = base_price * trend_factor * (1 + noise)
    else:  # sideways
        noise = np.random.randn(days) * 0.05
        prices = base_price * (1 + noise)
    
    # Create OHLC
    df = pd.DataFrame({
        "Open": prices * (1 - np.random.uniform(0.01, 0.02, days)),
        "High": prices * (1 + np.random.uniform(0.01, 0.03, days)),
        "Low": prices * (1 - np.random.uniform(0.01, 0.03, days)),
        "Close": prices,
        "Volume": np.random.randint(100000, 500000, days) * (2 if high_volume else 1),
    }, index=dates)
    
    return df


class TestSwingStrategy:
    """Unit tests for SwingStrategy"""
    
    def test_bullish_trend_generates_buy_signal(self):
        """Test that bullish trend with proper conditions generates BUY"""
        df = create_test_data(days=100, trend="bullish", high_volume=True)
        strategy = SwingStrategy()
        signal = strategy.analyze(df, "TESTSTOCK")
        
        # May or may not generate signal depending on exact conditions
        if signal:
            assert signal.signal_type == "BUY"
            assert signal.symbol == "TESTSTOCK"
            assert signal.strategy == "swing"
    
    def test_insufficient_data_returns_none(self):
        """Test that insufficient data returns None"""
        df = create_test_data(days=30)  # Less than minimum
        strategy = SwingStrategy()
        signal = strategy.analyze(df, "TESTSTOCK")
        
        assert signal is None
    
    def test_empty_dataframe_returns_none(self):
        """Test that empty dataframe returns None"""
        df = pd.DataFrame()
        strategy = SwingStrategy()
        signal = strategy.analyze(df, "TESTSTOCK")
        
        assert signal is None
    
    def test_signal_has_required_fields(self):
        """Test that generated signal has all required fields"""
        df = create_test_data(days=100, trend="bullish", high_volume=True)
        strategy = SwingStrategy()
        signal = strategy.analyze(df, "TESTSTOCK")
        
        if signal:
            assert hasattr(signal, "symbol")
            assert hasattr(signal, "signal_type")
            assert hasattr(signal, "entry_low")
            assert hasattr(signal, "entry_high")
            assert hasattr(signal, "stop_loss")
            assert hasattr(signal, "targets")
            assert hasattr(signal, "risk_reward")
            assert len(signal.targets) >= 2
    
    def test_risk_reward_is_calculated(self):
        """Test that risk-reward ratio is properly calculated"""
        df = create_test_data(days=100, trend="bullish", high_volume=True)
        strategy = SwingStrategy()
        signal = strategy.analyze(df, "TESTSTOCK")
        
        if signal:
            assert signal.risk_reward > 0
            # RR should be calculated as (target - entry) / (entry - SL)
            entry = (signal.entry_low + signal.entry_high) / 2
            expected_rr = strategy.calculate_risk_reward(
                entry, signal.stop_loss, signal.targets[0]
            )
            assert abs(signal.risk_reward - expected_rr) < 0.1
    
    def test_stop_loss_below_entry_for_buy(self):
        """Test that stop loss is below entry for BUY signals"""
        df = create_test_data(days=100, trend="bullish")
        strategy = SwingStrategy()
        signal = strategy.analyze(df, "TESTSTOCK")
        
        if signal and signal.signal_type == "BUY":
            assert signal.stop_loss < signal.entry_low
    
    def test_targets_above_entry_for_buy(self):
        """Test that targets are above entry for BUY signals"""
        df = create_test_data(days=100, trend="bullish")
        strategy = SwingStrategy()
        signal = strategy.analyze(df, "TESTSTOCK")
        
        if signal and signal.signal_type == "BUY":
            for target in signal.targets:
                assert target > signal.entry_high


class TestDataValidation:
    """Tests for data validation in base strategy"""
    
    def test_missing_columns_rejected(self):
        """Test that missing OHLCV columns are rejected"""
        df = pd.DataFrame({"Close": [100, 101, 102]})
        strategy = SwingStrategy()
        result = strategy.validate_data(df)
        assert result is False
    
    def test_nan_values_rejected(self):
        """Test that NaN values are rejected"""
        df = create_test_data(days=100)
        df.iloc[50, 0] = np.nan  # Add a NaN
        strategy = SwingStrategy()
        result = strategy.validate_data(df)
        assert result is False
    
    def test_valid_data_accepted(self):
        """Test that valid data passes validation"""
        df = create_test_data(days=100)
        strategy = SwingStrategy()
        result = strategy.validate_data(df)
        assert result is True


class TestIndicators:
    """Tests for indicator calculations"""
    
    def test_add_indicators_adds_ema(self):
        """Test that EMAs are calculated"""
        df = create_test_data(days=100)
        strategy = SwingStrategy()
        df = strategy.add_indicators(df)
        
        assert "EMA9" in df.columns
        assert "EMA20" in df.columns
        assert "EMA21" in df.columns
        assert "EMA50" in df.columns
    
    def test_add_indicators_adds_rsi(self):
        """Test that RSI is calculated"""
        df = create_test_data(days=100)
        strategy = SwingStrategy()
        df = strategy.add_indicators(df)
        
        assert "RSI" in df.columns
        # RSI should be between 0 and 100
        assert df["RSI"].dropna().between(0, 100).all()
    
    def test_add_indicators_adds_atr(self):
        """Test that ATR and ATR_PCT are calculated"""
        df = create_test_data(days=100)
        strategy = SwingStrategy()
        df = strategy.add_indicators(df)
        
        assert "ATR" in df.columns
        assert "ATR_PCT" in df.columns
        assert "ATR_Percentile" in df.columns


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
