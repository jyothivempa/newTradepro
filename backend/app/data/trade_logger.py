"""
TradeEdge Pro - Trade Outcome Logger
Logs trade outcomes for post-analysis with MFE/MAE tracking.

V1.1 Feature: CSV-based logging for strategy validation.
"""
import csv
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)

# Trade log file path
TRADE_LOG_PATH = Path(__file__).parent.parent.parent / "data" / "trade_log.csv"

# CSV columns
TRADE_COLUMNS = [
    "symbol",
    "entry_date",
    "entry_price",
    "exit_date",
    "exit_price",
    "signal_type",
    "pnl_pct",
    "max_favorable_excursion",
    "max_adverse_excursion",
    "bars_held",
    "regime_at_entry",
    "regime_confidence",
    "signal_score",
    "strategy",
    "sector",
]


@dataclass
class TradeOutcome:
    """Trade outcome for logging"""
    symbol: str
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    signal_type: str  # BUY or SELL
    pnl_pct: float
    max_favorable_excursion: float  # MFE - best unrealized gain %
    max_adverse_excursion: float    # MAE - worst unrealized loss %
    bars_held: int
    regime_at_entry: str
    regime_confidence: float
    signal_score: int
    strategy: str = "swing"
    sector: str = ""
    
    def to_dict(self) -> dict:
        return asdict(self)


def _ensure_log_file():
    """Create trade log file with headers if it doesn't exist"""
    TRADE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    if not TRADE_LOG_PATH.exists():
        with open(TRADE_LOG_PATH, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=TRADE_COLUMNS)
            writer.writeheader()
        logger.info(f"Created trade log: {TRADE_LOG_PATH}")


def log_trade(outcome: TradeOutcome) -> None:
    """
    Append trade outcome to CSV log.
    
    Args:
        outcome: TradeOutcome dataclass with trade details
    """
    _ensure_log_file()
    
    try:
        with open(TRADE_LOG_PATH, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=TRADE_COLUMNS)
            writer.writerow(outcome.to_dict())
        logger.info(f"Logged trade: {outcome.symbol} {outcome.signal_type} ({outcome.pnl_pct:+.2f}%)")
    except Exception as e:
        logger.error(f"Failed to log trade: {e}")


def get_trade_history(
    start_date: Optional[str] = None,
    symbol: Optional[str] = None,
    strategy: Optional[str] = None,
) -> List[TradeOutcome]:
    """
    Load trade history from CSV with optional filters.
    
    Args:
        start_date: Filter trades on or after this date (YYYY-MM-DD)
        symbol: Filter by symbol
        strategy: Filter by strategy type
        
    Returns:
        List of TradeOutcome objects
    """
    _ensure_log_file()
    
    trades = []
    try:
        with open(TRADE_LOG_PATH, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Apply filters
                if start_date and row["entry_date"] < start_date:
                    continue
                if symbol and row["symbol"] != symbol:
                    continue
                if strategy and row["strategy"] != strategy:
                    continue
                
                trades.append(TradeOutcome(
                    symbol=row["symbol"],
                    entry_date=row["entry_date"],
                    entry_price=float(row["entry_price"]),
                    exit_date=row["exit_date"],
                    exit_price=float(row["exit_price"]),
                    signal_type=row["signal_type"],
                    pnl_pct=float(row["pnl_pct"]),
                    max_favorable_excursion=float(row["max_favorable_excursion"]),
                    max_adverse_excursion=float(row["max_adverse_excursion"]),
                    bars_held=int(row["bars_held"]),
                    regime_at_entry=row["regime_at_entry"],
                    regime_confidence=float(row["regime_confidence"]),
                    signal_score=int(row["signal_score"]),
                    strategy=row.get("strategy", "swing"),
                    sector=row.get("sector", ""),
                ))
    except Exception as e:
        logger.error(f"Failed to load trade history: {e}")
    
    return trades


def get_trade_stats(trades: List[TradeOutcome]) -> dict:
    """
    Calculate statistics from trade history.
    
    V1.2: Added Sharpe ratio, expectancy, and STT-adjusted returns.
    
    Returns:
        Dict with win rate, avg MFE/MAE, win rate by regime, Sharpe, expectancy.
    """
    if not trades:
        return {"error": "No trades to analyze"}
    
    winners = [t for t in trades if t.pnl_pct > 0]
    losers = [t for t in trades if t.pnl_pct <= 0]
    
    # Basic stats
    win_rate = len(winners) / len(trades) * 100
    avg_win = sum(t.pnl_pct for t in winners) / len(winners) if winners else 0
    avg_loss = sum(t.pnl_pct for t in losers) / len(losers) if losers else 0
    avg_mfe = sum(t.max_favorable_excursion for t in trades) / len(trades)
    avg_mae = sum(t.max_adverse_excursion for t in trades) / len(trades)
    avg_bars = sum(t.bars_held for t in trades) / len(trades)
    
    # Win rate by regime
    regime_stats = {}
    regimes = set(t.regime_at_entry for t in trades)
    for regime in regimes:
        regime_trades = [t for t in trades if t.regime_at_entry == regime]
        regime_winners = [t for t in regime_trades if t.pnl_pct > 0]
        if regime_trades:
            regime_stats[regime] = round(len(regime_winners) / len(regime_trades) * 100, 1)
    
    # === V1.2 ENHANCED METRICS ===
    
    # Expectancy: (Win% × AvgWin) - (Loss% × AvgLoss)
    win_pct = len(winners) / len(trades)
    loss_pct = len(losers) / len(trades)
    expectancy = (win_pct * avg_win) - (loss_pct * abs(avg_loss))
    
    # Sharpe Ratio (annualized, assuming daily returns)
    returns = [t.pnl_pct for t in trades]
    sharpe = calculate_sharpe_ratio(returns)
    
    # STT-adjusted total return
    total_return = sum(t.pnl_pct for t in trades)
    stt_adjusted = total_return - (len(trades) * STT_RATE * 100)  # STT per trade
    
    return {
        "totalTrades": len(trades),
        "winRate": round(win_rate, 1),
        "avgWinPct": round(avg_win, 2),
        "avgLossPct": round(avg_loss, 2),
        "avgMFE": round(avg_mfe, 2),
        "avgMAE": round(avg_mae, 2),
        "avgBarsHeld": round(avg_bars, 1),
        "winRateByRegime": regime_stats,
        # V1.2 metrics
        "expectancy": round(expectancy, 2),
        "sharpeRatio": round(sharpe, 2),
        "totalReturnPct": round(total_return, 2),
        "sttAdjustedReturnPct": round(stt_adjusted, 2),
    }


# === V1.2 METRIC FUNCTIONS ===

# STT Rate (0.1% for delivery trades)
STT_RATE = 0.001


def calculate_sharpe_ratio(returns: List[float], risk_free_annual: float = 0.06) -> float:
    """
    Calculate annualized Sharpe Ratio.
    
    Args:
        returns: List of trade returns (%)
        risk_free_annual: Annual risk-free rate (RBI repo ~6%)
    
    Returns:
        Annualized Sharpe Ratio
    """
    if not returns or len(returns) < 2:
        return 0.0
    
    import math
    
    avg_return = sum(returns) / len(returns)
    variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
    std_dev = math.sqrt(variance) if variance > 0 else 0.001
    
    # Assume ~250 trading days, adjust for avg bars held
    trades_per_year = 250 / max(1, sum(1 for _ in returns))
    
    # Daily risk-free
    risk_free_daily = risk_free_annual / 252
    
    # Sharpe = (Return - RiskFree) / StdDev * sqrt(N)
    sharpe = (avg_return - risk_free_daily) / std_dev * math.sqrt(min(trades_per_year, 50))
    
    return sharpe


def apply_stt(trade_value: float, is_intraday: bool = False) -> float:
    """
    Calculate STT (Securities Transaction Tax) for a trade.
    
    Args:
        trade_value: Total value of the trade
        is_intraday: True for intraday (0.025%), False for delivery (0.1%)
    
    Returns:
        STT amount to deduct
    """
    rate = 0.00025 if is_intraday else STT_RATE
    return trade_value * rate

