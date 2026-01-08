"""
Calibration Engine
Analyzes backtest results to find optimal score thresholds.
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Any
from app.engine.backtest import BacktestResult, Trade
from app.utils.logger import get_logger

logger = get_logger(__name__)

class CalibrationEngine:
    """
    Analyzes trades to determine the "Golden Score Threshold".
    Buckets trades by score and methodology.
    """
    
    def __init__(self, bucket_size: int = 5):
        self.bucket_size = bucket_size
        
    def analyze_results(self, backtest_results: List[BacktestResult]) -> Dict[str, Any]:
        """
        Aggregates all trades and analyzes performance by score bucket.
        """
        all_trades: List[Trade] = []
        for res in backtest_results:
            all_trades.extend(res.trades) # res.trades is list of dict or Trade objects?
            # res.trades in backtest.py is list of Dicts in to_dict(), but BacktestResult dataclass has field trades: List[Dict].
            # Wait, BacktestResult dataclass definition says trades: List[Dict].
            # But in run loop, I append Trade objects to `trades` list, then pass to _calculate_metrics.
            # in _calculate_metrics, I convert Trade objects to Dicts.
            # So `res.trades` contains Dicts.
            
        if not all_trades:
            return {"error": "No trades to analyze"}
            
        # Convert to DataFrame for easy analysis
        df = pd.DataFrame(all_trades)
        
        # Ensure we have 'score' and 'netPnl' columns
        if 'score' not in df.columns or 'netPnl' not in df.columns:
            return {"error": "Missing critical columns in trade data"}
            
        # Create Score Buckets
        bins = list(range(0, 105, self.bucket_size))
        labels = [f"{i}-{i+self.bucket_size}" for i in range(0, 100, self.bucket_size)]
        df['score_bucket'] = pd.cut(df['score'], bins=bins, labels=labels, right=False)
        
        # Aggregation Logic
        stats = df.groupby('score_bucket', observed=False).agg(
            trades=('score', 'count'),
            win_rate=('netPnl', lambda x: (x > 0).mean() * 100),
            avg_pnl=('netPnl', 'mean'),
            total_pnl=('netPnl', 'sum'),
            avg_return=('pnlPct', 'mean')
        ).reset_index()
        
        # Calculate Expectancy (WinRate% * AvgWin - LossRate% * AvgLoss) - Simplified here as Avg Return
        # Add Profit Factor
        # Need custom apply for Profit Factor
        
        bucket_metrics = []
        best_threshold = 0
        max_expectancy = -float('inf')
        
        for index, row in stats.iterrows():
            if row['trades'] == 0:
                continue
                
            bucket_trades = df[df['score_bucket'] == row['score_bucket']]
            gross_wins = bucket_trades[bucket_trades['netPnl'] > 0]['netPnl'].sum()
            gross_losses = abs(bucket_trades[bucket_trades['netPnl'] < 0]['netPnl'].sum())
            profit_factor = gross_wins / gross_losses if gross_losses > 0 else float('inf')
            
            # Simple expectancy = Avg PnL per trade
            expectancy = row['avg_pnl']
            
            metric = {
                "bucket": row['score_bucket'],
                "trades": int(row['trades']),
                "winRate": round(row['win_rate'], 1),
                "avgNetPnl": round(row['avg_pnl'], 2),
                "totalNetPnl": round(row['total_pnl'], 2),
                "profitFactor": round(profit_factor, 2),
                "avgReturnPct": round(row['avg_return'], 2)
            }
            bucket_metrics.append(metric)
            
            # Check for best threshold check (Cumulative logic would be better but per-bucket is start)
            if row['trades'] > 5 and row['win_rate'] > 50 and expectancy > max_expectancy:
                max_expectancy = expectancy
                # Extract lower bound of bucket
                try:
                    best_threshold = int(row['score_bucket'].split('-')[0])
                except: pass
                
        return {
            "metricsByBucket": bucket_metrics,
            "optimalThreshold": best_threshold,
            "totalTradesAnalyzed": len(df)
        }
