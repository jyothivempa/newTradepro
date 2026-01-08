"""
TradeEdge Pro - Backtesting Module
Validate strategies on historical data before trusting live signals
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

from app.strategies.base import Signal, BaseStrategy
from app.strategies.swing import SwingStrategy
from app.strategies.intraday_bias import IntradayBiasStrategy
from app.data.fetch_data import fetch_daily_data
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TransactionCosts:
    """Trading costs model"""
    brokerage_pct: float = 0.03  # 0.03% per leg
    stt_delivery_pct: float = 0.1  # 0.1% on Buy & Sell for delivery
    stt_intraday_pct: float = 0.025 # 0.025% on Sell only
    slippage_base: float = 0.05   # 0.05% base slippage
    
    def calculate(self, price: float, quantity: int, is_buy: bool, is_intraday: bool) -> dict:
        """Calculate costs for a single leg"""
        value = price * quantity
        brokerage = value * (self.brokerage_pct / 100)
        
        stt = 0.0
        if is_intraday:
            if not is_buy: # Sell side only for intraday
                stt = value * (self.stt_intraday_pct / 100)
        else: # Delivery (Swing)
            stt = value * (self.stt_delivery_pct / 100)
            
        return {"brokerage": brokerage, "stt": stt, "total": brokerage + stt}


@dataclass
class Trade:
    """Represents a single backtest trade"""
    symbol: str
    entry_date: datetime
    entry_index: int  # Added for candle-based counting
    entry_price: float
    quantity: int
    stop_loss: float
    target1: float
    target2: float
    signal_type: str
    score: int
    
    # Exit fields (filled after trade closes)
    exit_date: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: str = ""  # "target1", "target2", "stoploss", "time_exit"
    
    # PnL Metrics
    gross_pnl: float = 0.0
    net_pnl: float = 0.0
    pnl_pct: float = 0.0 # Net PnL %
    
    # Cost Breakdown
    commissions: float = 0.0
    taxes: float = 0.0
    slippage_loss: float = 0.0
    
    holding_days: int = 0
    is_winner: bool = False


@dataclass
class BacktestResult:
    """Complete backtest results with statistics"""
    strategy: str
    symbol: str
    start_date: str
    end_date: str
    
    # Trade metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    
    # Performance metrics (NET)
    win_rate: float = 0.0
    gross_profit: float = 0.0
    net_profit: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    avg_rr: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    
    # Risk metrics
    max_drawdown_pct: float = 0.0
    avg_holding_days: float = 0.0
    
    # Metrics by Score/Method (Calibration)
    metrics_by_score: Dict[str, Any] = field(default_factory=dict)
    
    # Trade list
    trades: List[Dict] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "symbol": self.symbol,
            "startDate": self.start_date,
            "endDate": self.end_date,
            "totalTrades": self.total_trades,
            "winningTrades": self.winning_trades,
            "losingTrades": self.losing_trades,
            "winRate": round(self.win_rate, 1),
            "netProfit": round(self.net_profit, 2),
            "avgWinPct": round(self.avg_win_pct, 2),
            "avgLossPct": round(self.avg_loss_pct, 2),
            "avgRR": round(self.avg_rr, 2),
            "profitFactor": round(self.profit_factor, 2),
            "expectancy": round(self.expectancy, 2),
            "maxDrawdownPct": round(self.max_drawdown_pct, 2),
            "avgHoldingDays": round(self.avg_holding_days, 1),
            "trades": self.trades,
            "metricsByScore": self.metrics_by_score,
        }


class Backtester:
    """
    Rolling window backtester with realistic cost/slippage modeling.
    """
    
    # Realism settings
    costs = TransactionCosts()
    GAP_SL_HANDLING = True
    NEXT_CANDLE_ENTRY = True
    
    def __init__(
        self,
        strategy: BaseStrategy,
        max_candles: int = 20, # Time-based exit (N bars)
        exit_at_target: int = 1,  # 1 = T1, 2 = T2
        initial_capital: float = 100000,
    ):
        self.strategy = strategy
        self.max_candles = max_candles
        self.exit_at_target = exit_at_target
        self.capital = initial_capital
    
    def apply_slippage(self, price: float, is_buy: bool, atr_pct: float = 1.0) -> float:
        """Apply dynamic slippage based on volatility"""
        # Base slippage 0.05%
        # If volatile (ATR > 2%), double slippage
        slippage_pct = self.costs.slippage_base
        if atr_pct > 2.0:
            slippage_pct *= 2.0
            
        slippage_mult = 1 + (slippage_pct / 100)
        
        # Buy higher, Sell lower
        actual_price = price * slippage_mult if is_buy else price / slippage_mult
        return actual_price
    
    def run(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        lookback_bars: int = 60,
    ) -> BacktestResult:
        """Run backtest on a single symbol."""
        logger.info(f"Starting backtest: {symbol} ({self.strategy.name})")
        
        # Fetch data
        df = fetch_daily_data(symbol, period="2y")
        if df is None or len(df) < lookback_bars + 50:
            logger.warning(f"Insufficient data for {symbol}")
            return BacktestResult(
                strategy=self.strategy.name,
                symbol=symbol,
                start_date=start_date or "",
                end_date=end_date or "",
            )
        
        # Parse dates
        if start_date:
            start_dt = pd.to_datetime(start_date)
        else:
            start_dt = df.index[-250] if len(df) > 250 else df.index[lookback_bars]
        
        if end_date:
            end_dt = pd.to_datetime(end_date)
        else:
            end_dt = df.index[-1]
        
        # Filter data range
        df = df[df.index <= end_dt]
        
        # Track trades
        trades: List[Trade] = []
        open_trade: Optional[Trade] = None
        equity_curve = [100.0]  # Start with 100
        
        # Rolling window simulation
        valid_indices = df.index[df.index >= start_dt]
        
        for i, current_date in enumerate(valid_indices):
            # Get data up to current bar (no look-ahead bias)
            current_idx = df.index.get_loc(current_date)
            
            if current_idx < lookback_bars:
                continue
            
            window = df.iloc[:current_idx + 1]
            current_bar = df.iloc[current_idx]
            
            # Check if we have an open trade
            if open_trade:
                # Check exit conditions
                high = current_bar['High']
                low = current_bar['Low']
                close = current_bar['Close']
                
                # Get ATR for dynamic slippage
                atr_pct = (current_bar['ATR'] / close * 100) if 'ATR' in current_bar else 1.0
                
                exit_price = 0.0
                exit_reason = ""
                
                holding_days = (current_date - open_trade.entry_date).days
                bars_held = current_idx - open_trade.entry_index
                
                if open_trade.signal_type == "BUY":
                    # GAP HANDLING: Check if opened below stop loss
                    if self.GAP_SL_HANDLING and current_bar['Open'] < open_trade.stop_loss:
                        # Gap down through SL - exit at open (worse than expected)
                        exit_price = self.apply_slippage(current_bar['Open'], False, atr_pct)
                        exit_reason = "gap_stoploss"
                    
                    # Check stop loss hit (worst case first)
                    elif low <= open_trade.stop_loss:
                        # Assume exit at SL price (with slippage)
                        exit_price = self.apply_slippage(open_trade.stop_loss, False, atr_pct)
                        exit_reason = "stoploss"
                    
                    # Check target 1
                    elif high >= open_trade.target1 and self.exit_at_target == 1:
                        exit_price = open_trade.target1 # Limit order, no slippage usually, or minimal
                        exit_reason = "target1"
                    
                    # Check target 2
                    elif high >= open_trade.target2 and self.exit_at_target == 2:
                        exit_price = open_trade.target2
                        exit_reason = "target2"
                    
                    # Check timeout per User Request (N candles)
                    elif bars_held >= self.max_candles:
                        exit_price = self.apply_slippage(close, False, atr_pct)
                        exit_reason = "time_exit"
                
                # If trade closed, process it
                if exit_price > 0:
                    open_trade.exit_date = current_date
                    open_trade.exit_price = exit_price
                    open_trade.exit_reason = exit_reason
                    open_trade.holding_days = holding_days
                    
                    # === COST CALCULATION ===
                    is_intraday = isinstance(self.strategy, IntradayBiasStrategy)
                    
                    # Entry Costs
                    entry_costs = self.costs.calculate(open_trade.entry_price, open_trade.quantity, True, is_intraday)
                    
                    # Exit Costs
                    exit_costs = self.costs.calculate(exit_price, open_trade.quantity, False, is_intraday)
                    
                    # Slippage Loss (Theoretical Entry - Actual Entry) + (Actual Exit - Theoretical Exit)
                    # Simplified: We already adjusted price via apply_slippage, so PnL reflects slippage.
                    # We can estimate slippage impact if needed, but Net PnL is what matters.
                    
                    open_trade.gross_pnl = (exit_price - open_trade.entry_price) * open_trade.quantity
                    
                    total_comm = entry_costs["brokerage"] + exit_costs["brokerage"]
                    total_tax = entry_costs["stt"] + exit_costs["stt"]
                    
                    open_trade.commissions = total_comm
                    open_trade.taxes = total_tax
                    open_trade.net_pnl = open_trade.gross_pnl - total_comm - total_tax
                    
                    open_trade.pnl_pct = (open_trade.net_pnl / (open_trade.entry_price * open_trade.quantity)) * 100
                    open_trade.is_winner = open_trade.net_pnl > 0
                    
                    trades.append(open_trade)
                    open_trade = None
            
            else:
                # No open trade - look for new signal
                signal = self.strategy.analyze(window, symbol)
                
                if signal and signal.score >= 70:
                    # Enter trade at next bar's open (simulated)
                    # We use Next Open as entry price
                    # But if we don't have next bar yet?
                    # In this loop logic, we are at 'i'. 
                    # If NEXT_CANDLE_ENTRY, we should enter at i+1 loop?
                    # The current logic handles "check if open trade" for EXIT.
                    # So if we generate signal at 'i', we enter at 'i+1'.
                    # This implies setting a "pending order".
                    # Simplified: We assume we enter at Lookahead Open? No, that's cheating.
                    # Correct way: Signal at Close of 'i'. Entry at Open of 'i+1'.
                    # So we store 'pending_signal' and execute next iteration?
                    # OR: We check signal at 'i-1'.
                    
                    # Existing logic was: analyze(window). window is up to 'i'.
                    # So signal is based on Close of 'i'.
                    # We can't enter at Open of 'i' because it passed.
                    # We enter at Open of 'i+1'.
                    # But 'i+1' is not available in this iteration?
                    # Actually, we can just say `entry_price = df.iloc[i+1]['Open']` if available.
                    # But that requires safe indexing.
                    
                    # Let's peek ahead safely
                    if i + 1 < len(df):
                        next_bar = df.iloc[i+1]
                        atr_pct = (df.iloc[i]['ATR'] / df.iloc[i]['Close'] * 100) if 'ATR' in df.columns else 1.0
                        
                        entry_price = self.apply_slippage(next_bar['Open'], True, atr_pct)
                        quantity = int(self.capital / entry_price)
                        if quantity < 1: quantity = 1 # fractional support? No.
                        
                        open_trade = Trade(
                            symbol=symbol,
                            entry_date=next_bar.name, # i+1 date
                            entry_index=i+1,  # Added: Store index for candle count
                            entry_price=entry_price,
                            quantity=quantity,
                            stop_loss=signal.stop_loss,
                            target1=signal.targets[0],
                            target2=signal.targets[1] if len(signal.targets) > 1 else signal.targets[0] * 1.05,
                            signal_type=signal.signal_type,
                            score=signal.score,
                        )
                        # We skip processing this trade in this iteration effectively, 
                        # it will be checked for exit in next iteration (which is i+1? No, i+2).
                        # Wait, i+1 iteration will see `open_trade`?
                        # Yes. But `open_trade.entry_date` is `current_date` of i+1.
                        # holding_days logic: (current_date - entry_date). 
                        # At i+1: current_date == entry_date. diff = 0.
                        # It will check Low/High of i+1. 
                        # So if i+1 bar hits SL, we exit immediately. That is correct.
                        pass
        
        # Close any remaining open trade
        if open_trade:
            # Force close at end
            last_bar = df.iloc[-1]
            exit_price = last_bar['Close'] # No slippage on MTM? apply anyway
            atr_pct = 1.0
            
            # Apply costs
            open_trade.exit_date = df.index[-1]
            open_trade.exit_price = self.apply_slippage(exit_price, False, atr_pct)
            open_trade.exit_reason = "end_of_backtest"
            
            # Recalculate PnL
            open_trade.gross_pnl = (open_trade.exit_price - open_trade.entry_price) * open_trade.quantity
            
            is_intraday = isinstance(self.strategy, IntradayBiasStrategy)
            entry_costs = self.costs.calculate(open_trade.entry_price, open_trade.quantity, True, is_intraday)
            exit_costs = self.costs.calculate(open_trade.exit_price, open_trade.quantity, False, is_intraday)
            
            total_comm = entry_costs["brokerage"] + exit_costs["brokerage"]
            total_tax = entry_costs["stt"] + exit_costs["stt"]
            
            open_trade.commissions = total_comm
            open_trade.taxes = total_tax
            open_trade.net_pnl = open_trade.gross_pnl - total_comm - total_tax
            open_trade.pnl_pct = (open_trade.net_pnl / (open_trade.entry_price * open_trade.quantity)) * 100
            
            trades.append(open_trade)
        
        # Calculate metrics
        return self._calculate_metrics(trades, equity_curve, symbol, start_dt, end_dt)
    
    def _calculate_metrics(
        self,
        trades: List[Trade],
        equity_curve: List[float],
        symbol: str,
        start_dt,
        end_dt,
    ) -> BacktestResult:
        """Calculate performance metrics from trades"""
        
        result = BacktestResult(
            strategy=self.strategy.name,
            symbol=symbol,
            start_date=str(start_dt.date()) if hasattr(start_dt, 'date') else str(start_dt),
            end_date=str(end_dt.date()) if hasattr(end_dt, 'date') else str(end_dt),
        )
        
        if not trades:
            return result
        
        result.total_trades = len(trades)
        result.winning_trades = sum(1 for t in trades if t.is_winner)
        result.losing_trades = result.total_trades - result.winning_trades
        
        # PnL Sums
        result.gross_profit = sum(t.gross_pnl for t in trades)
        result.net_profit = sum(t.net_pnl for t in trades)
        
        # Win rate
        result.win_rate = (result.winning_trades / result.total_trades * 100) if result.total_trades > 0 else 0
        
        # Average win/loss (Net PnL %)
        wins = [t.pnl_pct for t in trades if t.is_winner]
        losses = [abs(t.pnl_pct) for t in trades if not t.is_winner]
        
        result.avg_win_pct = np.mean(wins) if wins else 0
        result.avg_loss_pct = np.mean(losses) if losses else 0
        
        # Profit factor (Net Basis)
        gross_wins = sum(t.net_pnl for t in trades if t.net_pnl > 0)
        gross_losses = abs(sum(t.net_pnl for t in trades if t.net_pnl < 0))
        result.profit_factor = gross_wins / gross_losses if gross_losses > 0 else float('inf')
        
        # Expectancy (average expected gain per trade % NET)
        result.expectancy = (
            (result.win_rate / 100 * result.avg_win_pct) -
            ((100 - result.win_rate) / 100 * result.avg_loss_pct)
        )
        
        # Average R:R achieved
        rrs = [(t.pnl_pct / abs(((t.entry_price - t.stop_loss) / t.entry_price) * 100)) 
               for t in trades if t.entry_price != t.stop_loss]
        result.avg_rr = np.mean(rrs) if rrs else 0
        
        # Max drawdown
        equity = np.array(equity_curve)
        peak = np.maximum.accumulate(equity)
        drawdown = (peak - equity) / peak * 100
        result.max_drawdown_pct = np.max(drawdown) if len(drawdown) > 0 else 0
        
        # Average holding days
        result.avg_holding_days = np.mean([t.holding_days for t in trades]) if trades else 0
        
        # Trade list for analysis
        result.trades = [
            {
                "entryDate": str(t.entry_date.date()) if hasattr(t.entry_date, 'date') else str(t.entry_date),
                "exitDate": str(t.exit_date.date()) if hasattr(t.exit_date, 'date') else str(t.exit_date),
                "entryPrice": round(t.entry_price, 2),
                "exitPrice": round(t.exit_price, 2),
                "pnlPct": round(t.pnl_pct, 2),
                "netPnl": round(t.net_pnl, 2),
                "commissions": round(t.commissions, 2),
                "exitReason": t.exit_reason,
                "holdingDays": t.holding_days,
                "score": t.score,
            }
            for t in trades
        ]
        
        logger.info(
            f"Backtest complete: {symbol} | "
            f"Trades: {result.total_trades} | "
            f"Win Rate: {result.win_rate:.1f}% | "
            f"Net Profit: {result.net_profit:.2f}"
        )
        
        return result
    
    
def backtest_strategy(
    strategy_type: str,
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> BacktestResult:
    """
    Main entry point for backtesting a strategy on a symbol.
    
    Args:
        strategy_type: "swing" or "intraday_bias"
        symbol: Stock symbol (e.g., "RELIANCE", "TCS")
        start_date: Start date (YYYY-MM-DD), default 1 year ago
        end_date: End date, default today
    
    Returns:
        BacktestResult with trades and performance metrics
    """
    # Select strategy
    if strategy_type == "swing":
        strategy = SwingStrategy()
    elif strategy_type == "intraday_bias":
        strategy = IntradayBiasStrategy()
    else:
        raise ValueError(f"Unknown strategy: {strategy_type}")
    
    backtester = Backtester(
        strategy=strategy,
        max_candles=20 if strategy_type == "swing" else 1, # Time Exit: 20 bars Swing, 1 bar Intraday (EOD)
        exit_at_target=1,
        initial_capital=100000,
    )
    
    return backtester.run(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
    )


def backtest_portfolio(
    strategy_type: str,
    symbols: List[str],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run backtest across multiple symbols and aggregate results.
    
    Returns:
        Aggregated portfolio metrics + individual symbol results
    """
    results = []
    
    for symbol in symbols:
        try:
            result = backtest_strategy(strategy_type, symbol, start_date, end_date)
            if result.total_trades > 0:
                results.append(result)
        except Exception as e:
            logger.error(f"Backtest failed for {symbol}: {e}")
    
    if not results:
        return {"error": "No valid backtest results"}
    
    # Aggregate metrics
    total_trades = sum(r.total_trades for r in results)
    total_wins = sum(r.winning_trades for r in results)
    
    return {
        "strategy": strategy_type,
        "symbolCount": len(results),
        "totalTrades": total_trades,
        "overallWinRate": round((total_wins / total_trades) * 100, 1) if total_trades > 0 else 0,
        "avgExpectancy": round(np.mean([r.expectancy for r in results]), 2),
        "avgMaxDrawdown": round(np.mean([r.max_drawdown_pct for r in results]), 2),
        "symbols": [r.to_dict() for r in results],
    }
