"""
TradeEdge Pro - Expectancy Tracker (V2.3)

Tracks rolling win rates and expectancy by:
- Strategy (swing, intraday_bias)
- Market Regime (TRENDING, RANGING, VOLATILE)
- Symbol Type (index vs stock)

Replaces static 40% win rate assumption with adaptive estimates.
"""
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
from dataclasses import dataclass

from app.utils.logger import get_logger

logger = get_logger(__name__)

# Database path
DB_PATH = Path(__file__).parent.parent.parent / "data_cache" / "expectancy.db"


@dataclass
class ExpectancyEstimate:
    """Expectancy estimate for a strategy/regime combination"""
    strategy: str
    regime: str
    symbol_type: str
    
    # Rolling window stats (last 50 trades)
    total_trades: int
    winning_trades: int
    win_rate: float
    avg_win_r: float
    avg_loss_r: float
    expectancy: float
    
    # V2.6: Confidence weighting
    confidence: float  # 0-1 based on sample size (trades/50)
    
    # Metadata
    last_updated: str
    sample_size_adequate: bool  # True if >= 20 trades
    
    def get_weighted_expectancy(self) -> float:
        """
        Return confidence-weighted expectancy.
        
        Prevents over-reacting to small sample sizes.
        Example:
        - 10 trades: confidence=0.2, weighted_exp = raw_exp * 0.2
        - 50 trades: confidence=1.0, weighted_exp = raw_exp * 1.0
        
        Use this in production instead of raw expectancy.
        """
        return self.expectancy * self.confidence


def get_connection() -> sqlite3.Connection:
    """Get database connection, create tables if needed"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    
    # Create tables
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trade_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy TEXT NOT NULL,
            regime TEXT NOT NULL,
            symbol TEXT NOT NULL,
            symbol_type TEXT NOT NULL,
            won BOOLEAN NOT NULL,
            r_multiple REAL NOT NULL,
            entry_date TEXT NOT NULL,
            exit_date TEXT NOT NULL,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_trade_results_lookup 
        ON trade_results(strategy, regime, symbol_type, timestamp DESC)
    """)
    
    conn.commit()
    return conn


def record_trade_result(
    strategy: str,
    regime: str,
    symbol: str,
    won: bool,
    r_multiple: float,
    entry_date: str,
    exit_date: str
) -> None:
    """
    Record a trade result for expectancy tracking.
    
    Args:
        strategy: "swing" or "intraday_bias"
        regime: Market regime during trade (e.g., "TRENDING")
        symbol: Stock symbol
        won: True if profitable, False if loss
        r_multiple: R-multiple result (e.g., 2.5 for 2.5R win, -1.0 for full loss)
        entry_date: Entry date (YYYY-MM-DD)
        exit_date: Exit date (YYYY-MM-DD)
    """
    try:
        # Determine symbol type
        symbol_type = "index" if symbol.startswith("^") else "stock"
        
        conn = get_connection()
        conn.execute("""
            INSERT INTO trade_results 
            (strategy, regime, symbol, symbol_type, won, r_multiple, entry_date, exit_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (strategy, regime, symbol, symbol_type, int(won), r_multiple, entry_date, exit_date))
        conn.commit()
        
        logger.debug(f"Recorded trade result: {symbol} {strategy} {regime} Won={won} R={r_multiple:.2f}")
    except Exception as e:
        logger.error(f"Failed to record trade result: {e}")


def get_expectancy_estimate(
    strategy: str,
    regime: str = "ALL",
    symbol_type: str = "stock",
    window_trades: int = 50,
    min_trades: int = 20
) -> ExpectancyEstimate:
    """
    Get rolling expectancy estimate for a strategy/regime combination.
    
    Args:
        strategy: "swing" or "intraday_bias"
        regime: Market regime (or "ALL" for all regimes)
        symbol_type: "stock" or "index"
        window_trades: Number of recent trades to analyze (default 50)
        min_trades: Minimum trades for adequate sample (default 20)
    
    Returns:
        ExpectancyEstimate with rolling statistics
    """
    try:
        conn = get_connection()
        
        # Build query
        if regime == "ALL":
            query = """
                SELECT won, r_multiple FROM trade_results
                WHERE strategy = ? AND symbol_type = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """
            params = (strategy, symbol_type, window_trades)
        else:
            query = """
                SELECT won, r_multiple FROM trade_results
                WHERE strategy = ? AND regime = ? AND symbol_type = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """
            params = (strategy, regime, symbol_type, window_trades)
        
        rows = conn.execute(query, params).fetchall()
        
        if not rows:
            # No historical data - use conservative defaults
            logger.warning(f"No expectancy data for {strategy}/{regime}/{symbol_type}, using defaults")
            return ExpectancyEstimate(
                strategy=strategy,
                regime=regime,
                symbol_type=symbol_type,
                total_trades=0,
                winning_trades=0,
                win_rate=0.40,  # Conservative default
                avg_win_r=2.0,
                avg_loss_r=1.0,
                expectancy=0.0,
                confidence=0.0,  # No confidence in default values
                last_updated=datetime.now().isoformat(),
                sample_size_adequate=False
            )
        
        # Calculate rolling stats
        total = len(rows)
        winners = sum(1 for r in rows if r['won'])
        win_rate = winners / total if total > 0 else 0.0
        
        # Calculate average R-multiples
        winning_rs = [r['r_multiple'] for r in rows if r['won'] and r['r_multiple'] > 0]
        losing_rs = [abs(r['r_multiple']) for r in rows if not r['won']]
        
        avg_win_r = sum(winning_rs) / len(winning_rs) if winning_rs else 2.0
        avg_loss_r = sum(losing_rs) / len(losing_rs) if losing_rs else 1.0
        
        # Expectancy formula: E = (Win% × AvgWin) - (Loss% × AvgLoss)
        expectancy = (win_rate * avg_win_r) - ((1 - win_rate) * avg_loss_r)
        
        # V2.6: Confidence weighting based on sample size
        confidence = min(total / 50, 1.0)  # Full confidence at 50+ trades
        
        adequate = total >= min_trades
        
        logger.info(
            f"Expectancy estimate for {strategy}/{regime}/{symbol_type}: "
            f"Win={win_rate:.1%}, AvgWin={avg_win_r:.2f}R, AvgLoss={avg_loss_r:.2f}R, "
            f"E={expectancy:.2f}R, Confidence={confidence:.1%} (n={total}, adequate={adequate})"
        )
        
        return ExpectancyEstimate(
            strategy=strategy,
            regime=regime,
            symbol_type=symbol_type,
            total_trades=total,
            winning_trades=winners,
            win_rate=win_rate,
            avg_win_r=avg_win_r,
            avg_loss_r=avg_loss_r,
            expectancy=expectancy,
            confidence=confidence,
            last_updated=datetime.now().isoformat(),
            sample_size_adequate=adequate
        )
        
    except Exception as e:
        logger.error(f"Failed to get expectancy estimate: {e}")
        # Return conservative defaults on error
        return ExpectancyEstimate(
            strategy=strategy,
            regime=regime,
            symbol_type=symbol_type,
            total_trades=0,
            winning_trades=0,
            win_rate=0.40,
            avg_win_r=2.0,
            avg_loss_r=1.0,
            expectancy=0.0,
            last_updated=datetime.now().isoformat(),
            sample_size_adequate=False
        )


def get_all_expectancies() -> Dict[Tuple[str, str], ExpectancyEstimate]:
    """
    Get expectancy estimates for all strategy/regime combinations.
    
    Returns:
        Dict mapping (strategy, regime) -> ExpectancyEstimate
    """
    strategies = ["swing", "intraday_bias"]
    regimes = ["TRENDING", "RANGING", "VOLATILE", "ALL"]
    
    results = {}
    for strategy in strategies:
        for regime in regimes:
            estimate = get_expectancy_estimate(strategy, regime)
            results[(strategy, regime)] = estimate
    
    return results


def cleanup_old_results(days: int = 365) -> int:
    """Remove trade results older than X days"""
    try:
        conn = get_connection()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        cursor = conn.execute(
            "DELETE FROM trade_results WHERE timestamp < ?",
            (cutoff,)
        )
        conn.commit()
        deleted = cursor.rowcount
        logger.info(f"Cleaned up {deleted} old trade results (>{days} days)")
        return deleted
    except Exception as e:
        logger.error(f"Failed to cleanup old results: {e}")
        return 0
