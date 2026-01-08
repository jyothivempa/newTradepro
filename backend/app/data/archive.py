"""
TradeEdge Pro - Signal Archive
SQLite storage for all signals (accepted + rejected)
Enables future ML training and strategy analysis
"""
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
import json

from app.utils.logger import get_logger

logger = get_logger(__name__)

# Database path
DB_PATH = Path(__file__).parent.parent.parent / "data_cache" / "signals.db"


def get_connection() -> sqlite3.Connection:
    """Get database connection, create tables if needed"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    
    # Create tables
    conn.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            strategy TEXT NOT NULL,
            signal_type TEXT,
            score INTEGER,
            score_breakdown TEXT,
            entry_low REAL,
            entry_high REAL,
            stop_loss REAL,
            targets TEXT,
            risk_reward REAL,
            trend_strength TEXT,
            sector TEXT,
            rejected INTEGER DEFAULT 0,
            rejection_reason TEXT,
            nifty_trend TEXT,
            metadata TEXT,
            timestamp TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Simple schema migration: Add metadata column if missing
    try:
        conn.execute("ALTER TABLE signals ADD COLUMN metadata TEXT")
    except sqlite3.OperationalError:
        pass  # Column likely exists
    
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_signals_strategy ON signals(strategy)
    """)
    
    conn.commit()
    return conn


def archive_signal(
    symbol: str,
    strategy: str,
    signal_type: Optional[str] = None,
    score: int = 0,
    score_breakdown: Optional[Dict] = None,
    entry_low: float = 0,
    entry_high: float = 0,
    stop_loss: float = 0,
    targets: Optional[List[float]] = None,
    risk_reward: float = 0,
    trend_strength: str = "",
    sector: str = "",
    rejected: bool = False,
    rejection_reason: str = "",
    nifty_trend: str = "neutral",
    metadata: Optional[Dict] = None,
) -> int:
    """
    Archive a signal (accepted or rejected).
    Returns the signal ID.
    """
    try:
        conn = get_connection()
        cursor = conn.execute("""
            INSERT INTO signals (
                symbol, strategy, signal_type, score, score_breakdown,
                entry_low, entry_high, stop_loss, targets, risk_reward,
                trend_strength, sector, rejected, rejection_reason,
                nifty_trend, metadata, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            symbol,
            strategy,
            signal_type,
            score,
            json.dumps(score_breakdown) if score_breakdown else None,
            entry_low,
            entry_high,
            stop_loss,
            json.dumps(targets) if targets else None,
            risk_reward,
            trend_strength,
            sector,
            1 if rejected else 0,
            rejection_reason,
            nifty_trend,
            json.dumps(metadata) if metadata else None,
            datetime.now().isoformat(),
        ))
        conn.commit()
        signal_id = cursor.lastrowid
        
        status = "REJECTED" if rejected else "ACCEPTED"
        logger.debug(f"Archived signal: {symbol} ({strategy}) - {status}")
        
        return signal_id
    
    except Exception as e:
        logger.error(f"Failed to archive signal {symbol}: {e}")
        return -1


def get_signal_history(
    symbol: Optional[str] = None,
    strategy: Optional[str] = None,
    days: int = 30,
    include_rejected: bool = True,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Get signal history with optional filters"""
    conn = get_connection()
    
    query = "SELECT * FROM signals WHERE 1=1"
    params = []
    
    if symbol:
        query += " AND symbol = ?"
        params.append(symbol)
    
    if strategy:
        query += " AND strategy = ?"
        params.append(strategy)
    
    if not include_rejected:
        query += " AND rejected = 0"
    
    query += f" AND timestamp >= datetime('now', '-{days} days')"
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    
    cursor = conn.execute(query, params)
    rows = cursor.fetchall()
    
    return [dict(row) for row in rows]


def get_strategy_stats(strategy: str, days: int = 30) -> Dict[str, Any]:
    """Get strategy performance stats"""
    conn = get_connection()
    
    # Total signals
    total = conn.execute("""
        SELECT COUNT(*) FROM signals 
        WHERE strategy = ? AND timestamp >= datetime('now', ? || ' days')
    """, (strategy, f"-{days}")).fetchone()[0]
    
    # Accepted signals
    accepted = conn.execute("""
        SELECT COUNT(*) FROM signals 
        WHERE strategy = ? AND rejected = 0 
        AND timestamp >= datetime('now', ? || ' days')
    """, (strategy, f"-{days}")).fetchone()[0]
    
    # Average score of accepted
    avg_score = conn.execute("""
        SELECT AVG(score) FROM signals 
        WHERE strategy = ? AND rejected = 0 
        AND timestamp >= datetime('now', ? || ' days')
    """, (strategy, f"-{days}")).fetchone()[0] or 0
    
    # Top rejection reasons
    rejections = conn.execute("""
        SELECT rejection_reason, COUNT(*) as count FROM signals 
        WHERE strategy = ? AND rejected = 1 
        AND timestamp >= datetime('now', ? || ' days')
        GROUP BY rejection_reason ORDER BY count DESC LIMIT 5
    """, (strategy, f"-{days}")).fetchall()
    
    return {
        "strategy": strategy,
        "days": days,
        "totalSignals": total,
        "acceptedSignals": accepted,
        "rejectedSignals": total - accepted,
        "acceptRate": round((accepted / total * 100) if total > 0 else 0, 1),
        "avgScore": round(avg_score, 1),
        "topRejectionReasons": [{"reason": r[0], "count": r[1]} for r in rejections],
    }


def cleanup_old_signals(days: int = 90) -> int:
    """Remove signals older than X days"""
    conn = get_connection()
    cursor = conn.execute("""
        DELETE FROM signals WHERE timestamp < datetime('now', ? || ' days')
    """, (f"-{days}",))
    conn.commit()
    deleted = cursor.rowcount
    logger.info(f"Cleaned up {deleted} old signals (>{days} days)")
    return deleted
