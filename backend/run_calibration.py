
import asyncio
import sys
import os
import pandas as pd
from datetime import datetime, timedelta

# Add backend to path
sys.path.append(os.getcwd())

from app.engine.backtest import Backtester, TransactionCosts
from app.engine.calibration import CalibrationEngine
from app.engine.signal_generator import load_stock_universe
from app.utils.logger import get_logger

logger = get_logger(__name__)

async def run_calibration():
    print("\nStarting System Calibration Run...")
    
    # 1. Load Universe
    stocks = load_stock_universe()
    symbols = [s["symbol"] for s in stocks][:10] # Top 10 stocks
    print(f"  Loaded {len(symbols)} stocks for calibration")
    
    # 2. Run Backtest
    print("  Running Backtests (Swing Strategy)...")
    from app.strategies.swing import SwingStrategy
    strategy = SwingStrategy()
    backtester = Backtester(strategy=strategy, initial_capital=100000)
    
    results = []
    
    for symbol in symbols:
        try:
            from app.data.fetch_data import fetch_daily_data
            df = fetch_daily_data(symbol, period="2y")
            
            if df is None or df.empty:
                print(f"    {symbol}: No data")
                continue
                
            res = backtester.run(df, symbol)
            results.append(res)
            print(f"    {symbol}: {res.total_trades} trades, Net PnL: {res.net_profit:.2f}")
            
        except Exception as e:
            print(f"    Failed {symbol}: {e}")
            
    # 3. Analyze Results
    print("\nAnalyzing Calibration Data...")
    engine = CalibrationEngine(bucket_size=5)
    analysis = engine.analyze_results(results)
    
    if "metricsByBucket" in analysis:
        print("\nCalibration Results (Score vs Win Rate)")
        print(f"{'Score Range':<15} | {'Trades':<8} | {'Win Rate':<10} | {'Expectancy':<10} | {'Profit Factor':<10}")
        print("-" * 65)
        
        for b in analysis["metricsByBucket"]:
            print(f"{b['bucket']:<15} | {b['trades']:<8} | {b['winRate']:<10} | {b['expectancy']:<10} | {b['profitFactor']:<10}")
            
        print(f"\nOptimal Threshold: {analysis.get('optimalThreshold', 'N/A')}")
    else:
        print("  No trades generated to analyze.")

if __name__ == "__main__":
    asyncio.run(run_calibration())
