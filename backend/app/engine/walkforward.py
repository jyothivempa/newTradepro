"""
TradeEdge Pro - Walk-Forward Validation Engine (V2.2)

Rolling window backtesting to prevent overfitting and measure out-of-sample performance.

Window Structure:
  |---- Train (18mo) ----|----- Test (6mo) -----|
         |---- Train (18mo) ----|----- Test (6mo) -----|
                |---- Train (18mo) ----|----- Test (6mo) -----|
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import pandas as pd
import numpy as np

from app.engine.backtest import Backtester, BacktestResult
from app.strategies.swing import SwingStrategy
from app.strategies.intraday_bias import IntradayBiasStrategy
from app.data.fetch_data import fetch_daily_data
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class WalkForwardWindow:
    """Single train/test window result"""
    window_id: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    
    # Train Phase Metrics (In-Sample)
    train_trades: int = 0
    train_win_rate: float = 0.0
    train_expectancy: float = 0.0
    train_max_dd: float = 0.0
    
    # Test Phase Metrics (Out-of-Sample) - THE REAL NUMBER
    test_trades: int = 0
    test_win_rate: float = 0.0
    test_expectancy: float = 0.0
    test_max_dd: float = 0.0
    test_profit: float = 0.0
    
    # Regime at test phase
    test_regime: str = "NEUTRAL"
    
    def to_dict(self) -> dict:
        return {
            "windowId": self.window_id,
            "trainStart": self.train_start,
            "trainEnd": self.train_end,
            "testStart": self.test_start,
            "testEnd": self.test_end,
            "train": {
                "trades": self.train_trades,
                "winRate": round(self.train_win_rate, 1),
                "expectancy": round(self.train_expectancy, 2),
                "maxDD": round(self.train_max_dd, 2),
            },
            "test": {
                "trades": self.test_trades,
                "winRate": round(self.test_win_rate, 1),
                "expectancy": round(self.test_expectancy, 2),
                "maxDD": round(self.test_max_dd, 2),
                "profit": round(self.test_profit, 2),
                "regime": self.test_regime,
            }
        }


@dataclass
class WalkForwardResult:
    """Complete walk-forward analysis result"""
    symbol: str
    strategy: str
    total_windows: int
    data_start: str
    data_end: str
    
    # Aggregated Metrics
    stability_score: float = 0.0      # Consistency across windows (0-1)
    avg_test_expectancy: float = 0.0  # Average out-of-sample edge
    worst_window_dd: float = 0.0      # Worst drawdown in any test window
    best_window_expectancy: float = 0.0
    worst_window_expectancy: float = 0.0
    
    # Regime-wise performance
    regime_expectancy: Dict[str, float] = field(default_factory=dict)
    
    # All windows
    windows: List[WalkForwardWindow] = field(default_factory=list)
    
    # Verdict
    is_robust: bool = False  # True if stability > 0.6 and avg_expectancy > 0
    verdict: str = ""
    
    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "strategy": self.strategy,
            "totalWindows": self.total_windows,
            "dataStart": self.data_start,
            "dataEnd": self.data_end,
            "stabilityScore": round(self.stability_score, 2),
            "avgTestExpectancy": round(self.avg_test_expectancy, 2),
            "worstWindowDD": round(self.worst_window_dd, 2),
            "bestWindowExpectancy": round(self.best_window_expectancy, 2),
            "worstWindowExpectancy": round(self.worst_window_expectancy, 2),
            "regimeExpectancy": {k: round(v, 2) for k, v in self.regime_expectancy.items()},
            "windows": [w.to_dict() for w in self.windows],
            "isRobust": self.is_robust,
            "verdict": self.verdict,
        }


def calculate_stability_score(expectancies: List[float]) -> float:
    """
    Calculate stability score based on consistency of expectancies.
    
    Formula: 1 - (std / abs(mean)) if mean != 0, else 0
    Higher = more consistent performance across windows.
    """
    if len(expectancies) < 2:
        return 0.0
    
    arr = np.array(expectancies)
    mean = np.mean(arr)
    std = np.std(arr)
    
    if abs(mean) < 0.001:
        return 0.0
    
    # Coefficient of variation inverted
    cv = std / abs(mean)
    stability = max(0, 1 - cv)
    
    return min(1.0, stability)


def run_walkforward(
    symbol: str,
    strategy: str = "swing",
    train_months: int = 18,
    test_months: int = 6,
    step_months: int = 6,  # How much to roll forward each window
    data_years: int = 5,   # Total data to use
) -> WalkForwardResult:
    """
    Run walk-forward validation on a symbol.
    
    Args:
        symbol: Stock symbol (e.g., "RELIANCE.NS")
        strategy: "swing" or "intraday_bias"
        train_months: Training window length (default 18)
        test_months: Testing window length (default 6)
        step_months: How many months to roll forward (default 6)
        data_years: Total historical data to use (default 5)
    
    Returns:
        WalkForwardResult with all windows and aggregated metrics
    """
    logger.info(f"🔄 Starting Walk-Forward: {symbol} ({strategy}) | Train={train_months}m, Test={test_months}m")
    
    # Fetch extended data
    df = fetch_daily_data(symbol, period=f"{data_years}y")
    if df is None or len(df) < 252:  # Need at least 1 year
        logger.warning(f"Insufficient data for {symbol}")
        return WalkForwardResult(
            symbol=symbol,
            strategy=strategy,
            total_windows=0,
            data_start="",
            data_end="",
            verdict="INSUFFICIENT_DATA"
        )
    
    data_start = df.index[0]
    data_end = df.index[-1]
    
    # Initialize strategy
    if strategy == "swing":
        strat = SwingStrategy()
    else:
        strat = IntradayBiasStrategy()
    
    backtester = Backtester(strategy=strat, max_candles=20)
    
    # Generate windows
    windows: List[WalkForwardWindow] = []
    window_id = 0
    
    # First window starts at data_start
    train_start = data_start
    
    while True:
        # Calculate window boundaries
        train_end = train_start + relativedelta(months=train_months)
        test_start = train_end + timedelta(days=1)
        test_end = test_start + relativedelta(months=test_months)
        
        # Check if test_end exceeds data
        if test_end > data_end:
            break
        
        window_id += 1
        logger.info(f"  Window {window_id}: Train {train_start.date()} - {train_end.date()}, Test {test_start.date()} - {test_end.date()}")
        
        # === TRAIN PHASE ===
        train_result = backtester.run(
            symbol=symbol,
            start_date=train_start.strftime("%Y-%m-%d"),
            end_date=train_end.strftime("%Y-%m-%d"),
        )
        
        # === TEST PHASE ===
        test_result = backtester.run(
            symbol=symbol,
            start_date=test_start.strftime("%Y-%m-%d"),
            end_date=test_end.strftime("%Y-%m-%d"),
        )
        
        # Get test regime (dominant during test period)
        # Simplified: Use the regime from the regime engine on test data
        test_regime = "NEUTRAL"
        try:
            from app.engine.regime_engine import classify_regime_v2
            test_df = df[(df.index >= test_start) & (df.index <= test_end)]
            if len(test_df) > 50:
                regime_vector = classify_regime_v2(test_df)
                test_regime = regime_vector.dominant.value
        except Exception as e:
            logger.debug(f"Regime classification failed: {e}")
        
        # Create window record
        window = WalkForwardWindow(
            window_id=window_id,
            train_start=train_start.strftime("%Y-%m-%d"),
            train_end=train_end.strftime("%Y-%m-%d"),
            test_start=test_start.strftime("%Y-%m-%d"),
            test_end=test_end.strftime("%Y-%m-%d"),
            train_trades=train_result.total_trades,
            train_win_rate=train_result.win_rate,
            train_expectancy=train_result.expectancy,
            train_max_dd=train_result.max_drawdown_pct,
            test_trades=test_result.total_trades,
            test_win_rate=test_result.win_rate,
            test_expectancy=test_result.expectancy,
            test_max_dd=test_result.max_drawdown_pct,
            test_profit=test_result.net_profit,
            test_regime=test_regime,
        )
        windows.append(window)
        
        # Roll forward
        train_start = train_start + relativedelta(months=step_months)
    
    if not windows:
        return WalkForwardResult(
            symbol=symbol,
            strategy=strategy,
            total_windows=0,
            data_start=data_start.strftime("%Y-%m-%d"),
            data_end=data_end.strftime("%Y-%m-%d"),
            verdict="NO_WINDOWS_GENERATED"
        )
    
    # === AGGREGATE METRICS ===
    test_expectancies = [w.test_expectancy for w in windows]
    test_dds = [w.test_max_dd for w in windows]
    
    # Stability Score
    stability = calculate_stability_score(test_expectancies)
    
    # Average/Best/Worst
    avg_expectancy = np.mean(test_expectancies)
    best_expectancy = max(test_expectancies)
    worst_expectancy = min(test_expectancies)
    worst_dd = min(test_dds) if test_dds else 0.0  # Most negative
    
    # Regime-wise expectancy
    regime_map: Dict[str, List[float]] = {}
    for w in windows:
        if w.test_regime not in regime_map:
            regime_map[w.test_regime] = []
        regime_map[w.test_regime].append(w.test_expectancy)
    
    regime_expectancy = {k: np.mean(v) for k, v in regime_map.items()}
    
    # Verdict
    is_robust = stability > 0.5 and avg_expectancy > 0
    if is_robust:
        verdict = "ROBUST: Strategy shows consistent positive edge across time periods."
    elif avg_expectancy > 0:
        verdict = "MARGINAL: Positive edge but high variance. Use with caution."
    else:
        verdict = "WEAK: Negative or inconsistent out-of-sample performance."
    
    result = WalkForwardResult(
        symbol=symbol,
        strategy=strategy,
        total_windows=len(windows),
        data_start=data_start.strftime("%Y-%m-%d"),
        data_end=data_end.strftime("%Y-%m-%d"),
        stability_score=stability,
        avg_test_expectancy=avg_expectancy,
        worst_window_dd=worst_dd,
        best_window_expectancy=best_expectancy,
        worst_window_expectancy=worst_expectancy,
        regime_expectancy=regime_expectancy,
        windows=windows,
        is_robust=is_robust,
        verdict=verdict,
    )
    
    
    logger.info(f"✅ Walk-Forward Complete: {symbol} | Windows={len(windows)}, Stability={stability:.2f}, AvgExp={avg_expectancy:.2f}")
    
    # V2.3: Fail-Fast Rule (Auto-Warning for Low Stability)
    if stability < 0.6 or avg_expectancy < 0:
        logger.critical(
            f"🚨 STRATEGY_UNSTABLE: {symbol} ({strategy}) | "
            f"Stability={stability:.2f} (threshold=0.6), "
            f"AvgExp={avg_expectancy:.2f} | "
            f"RECOMMENDATION: SUSPEND TRADING"
        )
        
        # Log to audit trail
        try:
            from app.core.audit import log_event
            log_event(
                event_type="STRATEGY_UNSTABLE_WARNING",
                metadata={
                    "symbol": symbol,
                    "strategy": strategy,
                    "stability_score": round(stability, 2),
                    "avg_test_expectancy": round(avg_expectancy, 2),
                    "verdict": verdict,
                    "windows": len(windows),
                    "recommendation": "SUSPEND_TRADING"
                }
            )
        except Exception as e:
            logger.error(f"Failed to log stability warning: {e}")
    
    return result

