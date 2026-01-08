"""
TradeEdge Pro - Portfolio Manager
Track actual trades taken from signals
"""
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional, Dict, Any
from pathlib import Path

from app.utils.logger import get_logger

logger = get_logger(__name__)

# Database path
DB_PATH = Path(__file__).parent / "portfolio.db"


@dataclass
class Trade:
    """Represents a user's actual trade"""
    symbol: str
    entry_date: str  # ISO format
    entry_price: float
    quantity: int
    stop_loss: float
    target: float
    
    # Optional
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    signal_id: str = ""  # Link to archived signal
    status: str = "OPEN"  # OPEN | CLOSED
    exit_date: Optional[str] = None
    exit_price: Optional[float] = None
    pnl: float = 0.0
    pnl_pct: float = 0.0
    notes: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "signalId": self.signal_id,
            "entryDate": self.entry_date,
            "entryPrice": self.entry_price,
            "quantity": self.quantity,
            "stopLoss": self.stop_loss,
            "target": self.target,
            "status": self.status,
            "exitDate": self.exit_date,
            "exitPrice": self.exit_price,
            "pnl": round(self.pnl, 2),
            "pnlPct": round(self.pnl_pct, 2),
            "notes": self.notes,
            "createdAt": self.created_at,
        }


def _get_connection() -> sqlite3.Connection:
    """Get database connection"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_portfolio_db():
    """Initialize portfolio database"""
    conn = _get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            signal_id TEXT,
            entry_date TEXT NOT NULL,
            entry_price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            stop_loss REAL NOT NULL,
            target REAL NOT NULL,
            status TEXT DEFAULT 'OPEN',
            exit_date TEXT,
            exit_price REAL,
            pnl REAL DEFAULT 0,
            pnl_pct REAL DEFAULT 0,
            notes TEXT,
            created_at TEXT
        )
    """)
    
    conn.commit()
    conn.close()
    logger.info("Portfolio database initialized")


def add_trade(trade: Trade) -> Trade:
    """Add a new trade to portfolio"""
    conn = _get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO trades (id, symbol, signal_id, entry_date, entry_price, 
                           quantity, stop_loss, target, status, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        trade.id, trade.symbol, trade.signal_id, trade.entry_date,
        trade.entry_price, trade.quantity, trade.stop_loss, trade.target,
        trade.status, trade.notes, trade.created_at
    ))
    
    conn.commit()
    conn.close()
    logger.info(f"Trade added: {trade.symbol} @ ₹{trade.entry_price}")
    return trade


def get_trades(status: Optional[str] = None) -> List[Trade]:
    """Get all trades, optionally filtered by status"""
    conn = _get_connection()
    cursor = conn.cursor()
    
    if status:
        cursor.execute("SELECT * FROM trades WHERE status = ? ORDER BY created_at DESC", (status,))
    else:
        cursor.execute("SELECT * FROM trades ORDER BY created_at DESC")
    
    rows = cursor.fetchall()
    conn.close()
    
    trades = []
    for row in rows:
        trades.append(Trade(
            id=row["id"],
            symbol=row["symbol"],
            signal_id=row["signal_id"] or "",
            entry_date=row["entry_date"],
            entry_price=row["entry_price"],
            quantity=row["quantity"],
            stop_loss=row["stop_loss"],
            target=row["target"],
            status=row["status"],
            exit_date=row["exit_date"],
            exit_price=row["exit_price"],
            pnl=row["pnl"] or 0,
            pnl_pct=row["pnl_pct"] or 0,
            notes=row["notes"] or "",
            created_at=row["created_at"] or "",
        ))
    
    return trades


def get_trade_by_id(trade_id: str) -> Optional[Trade]:
    """Get single trade by ID"""
    conn = _get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM trades WHERE id = ?", (trade_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return None
    
    return Trade(
        id=row["id"],
        symbol=row["symbol"],
        signal_id=row["signal_id"] or "",
        entry_date=row["entry_date"],
        entry_price=row["entry_price"],
        quantity=row["quantity"],
        stop_loss=row["stop_loss"],
        target=row["target"],
        status=row["status"],
        exit_date=row["exit_date"],
        exit_price=row["exit_price"],
        pnl=row["pnl"] or 0,
        pnl_pct=row["pnl_pct"] or 0,
        notes=row["notes"] or "",
        created_at=row["created_at"] or "",
    )


def update_trade(trade_id: str, updates: Dict[str, Any]) -> Optional[Trade]:
    """Update trade fields"""
    conn = _get_connection()
    cursor = conn.cursor()
    
    # Build update query dynamically
    allowed_fields = ["stop_loss", "target", "notes", "quantity"]
    set_clauses = []
    values = []
    
    for field in allowed_fields:
        if field in updates:
            set_clauses.append(f"{field} = ?")
            values.append(updates[field])
    
    if not set_clauses:
        conn.close()
        return get_trade_by_id(trade_id)
    
    values.append(trade_id)
    query = f"UPDATE trades SET {', '.join(set_clauses)} WHERE id = ?"
    
    cursor.execute(query, values)
    conn.commit()
    conn.close()
    
    logger.info(f"Trade updated: {trade_id}")
    return get_trade_by_id(trade_id)


def close_trade(trade_id: str, exit_price: float, exit_date: str = None) -> Optional[Trade]:
    """Close a trade with exit price and calculate P&L"""
    trade = get_trade_by_id(trade_id)
    if not trade:
        return None
    
    if trade.status == "CLOSED":
        logger.warning(f"Trade {trade_id} already closed")
        return trade
    
    # Calculate P&L
    pnl = (exit_price - trade.entry_price) * trade.quantity
    pnl_pct = ((exit_price - trade.entry_price) / trade.entry_price) * 100
    
    exit_dt = exit_date or datetime.now().strftime("%Y-%m-%d")
    
    conn = _get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE trades 
        SET status = 'CLOSED', exit_date = ?, exit_price = ?, pnl = ?, pnl_pct = ?
        WHERE id = ?
    """, (exit_dt, exit_price, pnl, pnl_pct, trade_id))
    
    conn.commit()
    conn.close()
    
    logger.info(f"Trade closed: {trade.symbol} | P&L: ₹{pnl:.2f} ({pnl_pct:.1f}%)")
    return get_trade_by_id(trade_id)


def delete_trade(trade_id: str) -> bool:
    """Delete a trade"""
    conn = _get_connection()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM trades WHERE id = ?", (trade_id,))
    deleted = cursor.rowcount > 0
    
    conn.commit()
    conn.close()
    
    if deleted:
        logger.info(f"Trade deleted: {trade_id}")
    return deleted


def get_portfolio_stats() -> Dict[str, Any]:
    """Get portfolio summary statistics"""
    trades = get_trades()
    
    open_trades = [t for t in trades if t.status == "OPEN"]
    closed_trades = [t for t in trades if t.status == "CLOSED"]
    
    # Calculate stats
    total_pnl = sum(t.pnl for t in closed_trades)
    winning_trades = [t for t in closed_trades if t.pnl > 0]
    losing_trades = [t for t in closed_trades if t.pnl <= 0]
    
    win_rate = (len(winning_trades) / len(closed_trades) * 100) if closed_trades else 0
    
    avg_win = sum(t.pnl for t in winning_trades) / len(winning_trades) if winning_trades else 0
    avg_loss = sum(t.pnl for t in losing_trades) / len(losing_trades) if losing_trades else 0
    
    # Calculate open position value
    open_value = sum(t.entry_price * t.quantity for t in open_trades)
    
    return {
        "totalTrades": len(trades),
        "openTrades": len(open_trades),
        "closedTrades": len(closed_trades),
        "totalPnl": round(total_pnl, 2),
        "winRate": round(win_rate, 1),
        "winningTrades": len(winning_trades),
        "losingTrades": len(losing_trades),
        "avgWin": round(avg_win, 2),
        "avgLoss": round(avg_loss, 2),
        "openPositionValue": round(open_value, 2),
    }


# Initialize database on module import
init_portfolio_db()
