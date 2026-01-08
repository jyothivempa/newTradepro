
import logging
import pandas as pd
import sys
import os
from datetime import datetime

# Add backend to path
sys.path.append(os.getcwd())
logging.basicConfig(level=logging.ERROR)

from app.engine.backtest import Backtester, Trade, TransactionCosts
from app.strategies.swing import SwingStrategy
from app.engine.calibration import CalibrationEngine, BacktestResult
from app.engine.risk_manager import RiskManager
from app.engine.market_regime import RegimeAnalysis, MarketRegime

def test_cost_modeling():
    print("\n[1] Testing Cost Modeling...")
    costs = TransactionCosts()
    entry_price = 1000.0
    quantity = 100
    
    # Calculate check
    res_entry = costs.calculate(entry_price, quantity, True, False) # Buy Swing
    res_exit = costs.calculate(entry_price * 1.1, quantity, False, False) # Sell Swing
    
    # Delivery Brokerage 0.03%, STT 0.1%
    expected_brokerage = (1000 * 100) * 0.0003
    expected_stt = (1000 * 100) * 0.001
    
    print(f"  Entry Brokerage: {res_entry['brokerage']:.4f} (Expected: {expected_brokerage:.4f})")
    print(f"  Entry STT: {res_entry['stt']:.4f} (Expected: {expected_stt:.4f})")
    
    if abs(res_entry['brokerage'] - expected_brokerage) < 0.1:
        print("  ✓ Brokerage Calc Correct")
    else:
        print("  X Brokerage Calc Failed")

def test_calibration():
    print("\n[2] Testing Calibration Engine...")
    
    # Create mock results
    trades = []
    # Good trades with high score
    for i in range(10):
        trades.append(Trade(
            symbol="TEST", entry_date=datetime.now(), entry_price=100, quantity=1, stop_loss=95, target1=105, target2=110,
            signal_type="BUY", score=85, net_pnl=5.0, pnl_pct=5.0, is_winner=True
        ))
    # Bad trades with low score
    for i in range(10):
        trades.append(Trade(
            symbol="TEST", entry_date=datetime.now(), entry_price=100, quantity=1, stop_loss=95, target1=105, target2=110,
            signal_type="BUY", score=65, net_pnl=-5.0, pnl_pct=-5.0, is_winner=False
        ))
        
    res = BacktestResult(
        strategy="swing", symbol="TEST", start_date="2024-01-01", end_date="2024-12-31",
        trades=[t.__dict__ for t in trades] # Calibration expects dicts or objects?
        # Calibration code says: pd.DataFrame(all_trades). If trades is list of objects, it works.
        # But BacktestResult.trades is List[Dict]. So passing dicts is correct.
    )
    # Actually wait, in Backtester.to_dict() we convert to dicts. But inside BacktestResult object it's List[Dict]?
    # Let's check definition. Field is trades: List[Dict].
    # So I pass dicts.
    
    # Fix: CalibrationEngine expects objects or dicts?
    # pd.DataFrame(all_trades) works with list of dicts.
    
    engine = CalibrationEngine(bucket_size=10)
    # We need to simulate BacktestResult having these trades
    # But wait, my Mock creation above made trades list of Trades for convenience, 
    # but I passed [t.__dict__] to BacktestResult.
    
    analysis = engine.analyze_results([res])
    
    if "metricsByBucket" in analysis:
        print("  ✓ Calibration Analysis Successful")
        for b in analysis["metricsByBucket"]:
            print(f"    Bucket {b['bucket']}: WinRate {b['winRate']}% (Trades: {b['trades']})")
    else:
        print(f"  X Calibration Failed: {analysis}")

def test_circuit_breaker():
    print("\n[3] Testing Circuit Breaker...")
    rm = RiskManager()
    
    # Test Normal
    ok, _ = rm.check_circuit_breaker(-0.5, "BUY")
    print(f"  Normal Market (-0.5%): Allowed? {ok}")
    
    # Test Crash
    ok_crash, reason = rm.check_circuit_breaker(-2.0, "BUY")
    print(f"  Crash Market (-2.0%): Allowed? {ok_crash} (Reason: {reason})")
    
    # Test Short in Crash
    ok_short, _ = rm.check_circuit_breaker(-2.0, "SELL")
    print(f"  Crash Market Short (-2.0%): Allowed? {ok_short}")
    
    if not ok_crash and ok_short:
        print("  ✓ Circuit Breaker Logic Correct")
    else:
        print("  X Circuit Breaker Failed")

if __name__ == "__main__":
    test_cost_modeling()
    test_calibration()
    test_circuit_breaker()
