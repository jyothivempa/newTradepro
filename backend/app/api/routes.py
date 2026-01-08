"""
TradeEdge Pro - Enhanced API Routes
With score breakdown and risk snapshot
"""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
import re
from datetime import datetime

from app.engine.signal_generator import generate_signals, get_cached_data, load_stock_universe, get_cached_regime
from app.engine.risk_manager import RiskManager, risk_manager
from app.data.cache_manager import cache
from app.data.archive import get_signal_history, get_strategy_stats
from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter(prefix="/api", tags=["signals"])


# ===== Response Models =====

class ScoreBreakdownResponse(BaseModel):
    base: int
    deductions: Dict[str, int]
    bonuses: Dict[str, int]
    final: int


class TechnicalDetails(BaseModel):
    emaAlignment: str
    rsi: float
    adx: float
    volumeRatio: float


class EntryRange(BaseModel):
    low: float
    high: float


class SignalResponse(BaseModel):
    symbol: str
    type: str
    signal: str
    entry: EntryRange
    stopLoss: float
    targets: List[float]
    score: int
    trendStrength: str
    riskReward: str
    timestamp: str
    validUntil: str
    technicals: TechnicalDetails
    scoreBreakdown: Optional[ScoreBreakdownResponse] = None
    sector: Optional[str] = None


class PositionSizeRequest(BaseModel):
    capital: float = Field(100000, gt=0, le=100000000, description="Total capital")
    risk_percent: float = Field(1.0, gt=0, le=10, description="Risk per trade %")
    entry: float = Field(..., gt=0, le=1000000, description="Entry price")
    stop_loss: float = Field(..., gt=0, le=1000000, description="Stop loss price")
    
    @model_validator(mode='after')
    def validate_sl_not_equal_entry(self):
        if self.entry == self.stop_loss:
            raise ValueError('Stop loss cannot equal entry price')
        return self


class PositionSizeResponse(BaseModel):
    shares: int
    positionValue: float
    riskAmount: float
    riskPercent: float
    valid: bool
    rejectionReason: str = ""


class RiskSnapshotResponse(BaseModel):
    capital: float
    riskPerTrade: float
    openTrades: int
    maxTrades: int
    riskUsedToday: float
    maxDailyRisk: float
    sectorExposure: Dict[str, float]


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    stockUniverse: str
    stockCount: int
    niftyTrend: str
    marketRegime: Optional[Dict[str, Any]] = None
    cacheStats: dict
    dbStats: Optional[Dict[str, Any]] = None


class StockInfo(BaseModel):
    symbol: str
    name: str
    sector: str


# ===== Endpoints =====

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check with NIFTY trend, regime, and DB stats"""
    stocks = load_stock_universe()
    
    # Get Cached Data
    from app.engine.signal_generator import get_cached_regime
    regime_analysis = get_cached_regime()
    
    regime_info = {
        "regime": regime_analysis.regime.value,
        "adx": round(regime_analysis.adx, 1),
        "atrPct": round(regime_analysis.atr_pct, 2),
    } if regime_analysis else None
    
    # Get DB Stats (Signals generated today)
    from app.data.archive import get_connection
    try:
        conn = get_connection()
        today = datetime.now().strftime("%Y-%m-%d")
        total = conn.execute("SELECT COUNT(*) FROM signals WHERE date(timestamp) >= ?", (today,)).fetchone()[0]
        accepted = conn.execute("SELECT COUNT(*) FROM signals WHERE date(timestamp) >= ? AND rejected = 0", (today,)).fetchone()[0]
        db_stats = {
            "signalsToday": total,
            "accepted": accepted,
            "rejected": total - accepted,
        }
    except Exception as e:
        logger.error(f"Health DB check failed: {e}")
        db_stats = {"error": str(e)}

    return HealthResponse(
        status="healthy",
        timestamp=datetime.now().isoformat(),
        stockUniverse=settings.stock_universe,
        stockCount=len(stocks),
        niftyTrend=regime_analysis.regime.value if regime_analysis else "UNKNOWN",
        marketRegime=regime_info,
        cacheStats=cache.get_stats(),
        dbStats=db_stats
    )


class IntradayBiasResponse(BaseModel):
    """V1.3: Bias Engine Response (No P&L)"""
    symbol: str
    bias: str
    confidence: float
    validFor: str
    reasoning: List[str]
    atrPct: float
    volumeRatio: float
    disclaimer: str
    sector: Optional[str] = None


@router.get("/intraday-bias", response_model=List[IntradayBiasResponse])
async def get_intraday_bias_signals(
    limit: int = Query(10, ge=1, le=50),
    sector: Optional[str] = Query(None),
):
    """
    Get intraday bias signals.
    
    ⚠️ V1.3: Returns directional bias only, NO entry/exit prices.
    Designed for directional verification, not trading.
    """
    logger.info(f"Fetching intraday-bias signals (limit={limit})")
    
    results = generate_signals(
        strategy_type="intraday_bias",
        market_regime="neutral",
        max_signals=limit,
    )
    
    # Filter by sector if requested
    if sector:
        results = [r for r in results if r.get("sector") == sector]
        
    response = []
    for r in results:
        signal = r["signal"]
        
        # Ensure we have an IntradayBias object (not standard Signal)
        if hasattr(signal, "bias"):
            response.append({
                "symbol": signal.symbol,
                "bias": signal.bias,
                "confidence": signal.confidence,
                "validFor": signal.valid_for,
                "reasoning": signal.reasoning,
                "atrPct": signal.atr_pct,
                "volumeRatio": signal.volume_ratio,
                "disclaimer": "Directional bias only. Not a trading signal.",
                "sector": r.get("sector")
            })
            
    return response[:limit]
    



@router.get("/swing", response_model=List[SignalResponse])
async def get_swing_signals(
    limit: int = Query(10, ge=1, le=50),
    sector: Optional[str] = Query(None),
):
    """Get swing signals with score breakdown"""
    logger.info(f"Fetching swing signals (limit={limit})")
    
    results = generate_signals(
        strategy_type="swing",
        market_regime="neutral",
        max_signals=limit,
    )
    
    if sector:
        results = [r for r in results if r.get("sector", "").lower() == sector.lower()]
    
    responses = []
    for r in results:
        signal = r["signal"]
        breakdown = r.get("breakdown")
        
        resp = SignalResponse(
            **signal.to_dict(),
            scoreBreakdown=ScoreBreakdownResponse(**breakdown.to_dict()) if breakdown else None,
            sector=r.get("sector"),
        )
        responses.append(resp)
    
    return responses


@router.get("/stocks", response_model=List[StockInfo])
async def get_stocks(sector: Optional[str] = Query(None)):
    """Get stocks in universe"""
    stocks = load_stock_universe()
    
    if sector:
        stocks = [s for s in stocks if s.get("sector", "").lower() == sector.lower()]
    
    return [StockInfo(**s) for s in stocks]


@router.get("/stocks/{symbol}")
async def get_stock_data(symbol: str):
    """Get stock OHLCV data for charting"""
    symbol = symbol.upper()
    stocks = load_stock_universe()
    valid_symbols = {s["symbol"] for s in stocks}
    
    if symbol not in valid_symbols:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")
    
    df = get_cached_data(symbol, "daily")
    
    if df is None or df.empty:
        raise HTTPException(status_code=503, detail=f"Data unavailable for {symbol}")
    
    df_json = df.tail(250).reset_index()
    df_json.columns = ["date", "open", "high", "low", "close", "volume"]
    df_json["date"] = df_json["date"].dt.strftime("%Y-%m-%d")
    
    stock_info = next((s for s in stocks if s["symbol"] == symbol), {})
    
    return {
        "symbol": symbol,
        "name": stock_info.get("name", symbol),
        "sector": stock_info.get("sector", ""),
        "data": df_json.to_dict(orient="records"),
    }


@router.get("/sectors")
async def get_sectors():
    """Get unique sectors"""
    stocks = load_stock_universe()
    sectors = sorted(set(s.get("sector", "") for s in stocks if s.get("sector")))
    return {"sectors": sectors}


@router.get("/risk-snapshot", response_model=RiskSnapshotResponse)
async def get_risk_snapshot():
    """Get current risk exposure snapshot"""
    snapshot = risk_manager.get_snapshot()
    return RiskSnapshotResponse(**snapshot.to_dict())


@router.post("/calculate-position", response_model=PositionSizeResponse)
async def calculate_position_size(request: PositionSizeRequest):
    """Calculate position size"""
    sl_distance = abs(request.entry - request.stop_loss)
    
    if sl_distance == 0:
        return PositionSizeResponse(
            shares=0,
            positionValue=0,
            riskAmount=0,
            riskPercent=0,
            valid=False,
            rejectionReason="Stop loss cannot equal entry",
        )
    
    risk_amount = request.capital * (request.risk_percent / 100)
    shares = int(risk_amount / sl_distance)
    position_value = shares * request.entry
    
    return PositionSizeResponse(
        shares=shares,
        positionValue=round(position_value, 2),
        riskAmount=round(risk_amount, 2),
        riskPercent=request.risk_percent,
        valid=True,
    )


@router.get("/nifty-trend")
async def get_nifty_trend_status():
    """Get current NIFTY trend status and regime"""
    from app.engine.signal_generator import get_cached_regime
    from app.engine.market_regime import MarketRegime
    
    regime_analysis = get_cached_regime()
    regime = regime_analysis.regime
    ema_slope = regime_analysis.ema_slope
    
    # Map regime to simple trend for compatibility
    if regime == MarketRegime.TRENDING:
        trend = "bullish" if ema_slope > 0 else "bearish"
    elif regime == MarketRegime.VOLATILE:
        trend = "volatile"
    else: # RANGING, DEAD
        trend = "neutral"
        
    return {
        "trend": trend,
        "regime": regime.value,
        "adx": round(regime_analysis.adx, 1),
        "description": f"Market is {regime.value} (ADX: {regime_analysis.adx:.1f})",
        "impact": "Follow Trend" if regime == MarketRegime.TRENDING else "Wait for Setup"
    }


@router.get("/nifty-regime-v2")
async def get_nifty_regime_vector():
    """
    Get probabilistic regime analysis for NIFTY50 (V2.0).
    
    Returns probability distribution instead of single label:
    - TRENDING, RANGING, VOLATILE, DEAD probabilities
    - Dominant regime with confidence
    - Supporting metrics: ADX, Choppiness, Hurst, ATR percentile
    - Position multiplier (weighted by regime probabilities)
    """
    from app.engine.regime_engine import get_nifty_regime_v2
    
    regime = get_nifty_regime_v2()
    
    return {
        **regime.to_dict(),
        "positionMultiplier": regime.get_position_multiplier(),
        "scoreAdjustment": regime.get_score_adjustment(),
    }


@router.get("/backtest/{symbol}")
async def run_backtest(
    symbol: str,
    strategy: str = Query("swing", description="Strategy: swing or intraday_bias"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
):
    """
    Run backtest for a strategy on a symbol.
    
    Returns trade history and performance metrics:
    - Win rate, Profit factor, Expectancy
    - Max drawdown, Average holding days
    - Individual trade list
    """
    from app.engine.backtest import backtest_strategy
    
    symbol = symbol.upper()
    
    try:
        result = backtest_strategy(
            strategy_type=strategy,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )
        return result.to_dict()
    except Exception as e:
        logger.error(f"Backtest failed for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signal-stats/{strategy}")
async def get_signal_stats(
    strategy: str,
    days: int = Query(30, ge=1, le=365),
):
    """Get strategy performance stats from signal archive"""
    from app.data.archive import get_strategy_stats
    
    return get_strategy_stats(strategy, days)


# ===== NEW: Advanced Features =====

@router.get("/news/{symbol}")
async def get_news_sentiment(symbol: str):
    """
    Get news sentiment for a stock.
    Returns sentiment score (-1 to +1) and recent articles.
    """
    from app.data.news_sentiment import get_stock_sentiment
    
    stocks = load_stock_universe()
    stock_info = next((s for s in stocks if s["symbol"] == symbol.upper()), {})
    
    return get_stock_sentiment(symbol.upper(), stock_info.get("name", ""))


@router.get("/fii-dii")
async def get_fii_dii_flow():
    """
    Get today's FII/DII trading activity.
    Returns net buy/sell and market bias.
    """
    from app.data.institutional_flow import get_fii_dii_data_sync
    
    return get_fii_dii_data_sync()


@router.get("/live/{symbol}")
async def get_live_quote(symbol: str):
    """
    Get live/delayed price for a stock.
    Note: 15-20 minute delay due to free data source.
    """
    from app.data.live_quotes import get_live_price
    
    return get_live_price(symbol.upper())


@router.get("/live")
async def get_live_quotes(symbols: str = Query(..., description="Comma-separated symbols")):
    """
    Get live prices for multiple stocks.
    Example: /api/live?symbols=RELIANCE,TCS,INFY
    """
    from app.data.live_quotes import get_live_prices
    
    symbol_list = [s.strip().upper() for s in symbols.split(",")]
    return get_live_prices(symbol_list)


@router.get("/market-status")
async def get_market_status():
    """Get current NSE market status (open/closed)"""
    from app.data.live_quotes import get_market_status
    
    return get_market_status()


@router.get("/data-sources/health")
async def get_data_source_health():
    """
    Get data source health status and metrics.
    
    Returns:
    - Overall health status (healthy/degraded)
    - Per-source metrics: success rate, failure count, last success/failure
    - Configuration: failure threshold, recovery period
    """
    from app.data.data_source_monitor import failure_tracker
    
    return failure_tracker.get_full_status()


@router.get("/economic-indicators")
async def get_economic_indicators_endpoint():
    """
    Get current RBI rates and economic context.
    
    Returns repo rate, CPI inflation, GDP growth, and rate bias.
    Requires: enable_economic_indicators = true in config
    """
    if not settings.enable_economic_indicators:
        raise HTTPException(
            status_code=400, 
            detail="Economic indicators disabled. Set enable_economic_indicators=true in .env"
        )
    
    from app.data.economic_indicators import get_rbi_data
    
    data = get_rbi_data()
    if data:
        return data.to_dict()
    raise HTTPException(status_code=503, detail="Unable to fetch economic data")


@router.get("/options-hint/{symbol}")
async def get_options_hint_endpoint(symbol: str):
    """
    Get options overlay suggestion for a stock signal.
    
    Returns covered call hint for low-volatility regimes.
    Requires: enable_options_hints = true in config
    """
    if not settings.enable_options_hints:
        raise HTTPException(
            status_code=400,
            detail="Options hints disabled. Set enable_options_hints=true in .env"
        )
    
    from app.strategies.options_hints import get_options_hint, calculate_covered_call_strike
    from app.engine.signal_generator import get_cached_regime, get_cached_data
    
    symbol = symbol.upper()
    regime = get_cached_regime()
    df = get_cached_data(symbol, "daily")
    
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail=f"No data for {symbol}")
    
    # Create a mock signal for the hint check
    from app.strategies.base import Signal
    current_price = df.iloc[-1]["Close"]
    
    mock_signal = Signal(
        symbol=symbol,
        signal_type="BUY",
        entry_low=current_price * 0.99,
        entry_high=current_price,
        stop_loss=current_price * 0.95,
        targets=[current_price * 1.05],
    )
    
    hint = get_options_hint(mock_signal, regime)
    
    if hint:
        strike = calculate_covered_call_strike(current_price, hint.suggested_strike_pct)
        return {
            "symbol": symbol,
            "currentPrice": round(current_price, 2),
            "regime": regime.regime.value,
            "hint": hint.to_dict(),
            "suggestedStrike": strike,
        }
    
    return {
        "symbol": symbol,
        "currentPrice": round(current_price, 2),
        "regime": regime.regime.value,
        "hint": None,
        "message": f"No options hint for {regime.regime.value} regime"
    }


@router.get("/trade-stats")
async def get_trade_stats_endpoint(
    start_date: str = None,
    symbol: str = None,
    strategy: str = None
):
    """
    Get trade outcome statistics from logged trades.
    
    V1.2: Now includes Sharpe ratio, expectancy, and STT-adjusted returns.
    """
    from app.data.trade_logger import get_trade_history, get_trade_stats
    
    trades = get_trade_history(start_date, symbol, strategy)
    
    if not trades:
        return {
            "message": "No trades logged yet",
            "totalTrades": 0,
        }
    
    stats = get_trade_stats(trades)
    return stats


class BacktestRequest(BaseModel):
    strategy: str = "swing"
    start_date: str = "2024-01-01"
    end_date: str = "2024-12-31"
    symbol: str = None


@router.post("/backtest")
async def run_backtest_endpoint(request: BacktestRequest):
    """
    Run backtest on historical data.
    
    V1.2 Feature: Web-based backtesting with full metrics.
    
    Returns:
        Win rate, Sharpe, expectancy, STT-adjusted return, win rate by regime
    """
    from app.engine.backtest import backtest_portfolio
    from app.data.nse_calendar import is_market_open
    
    symbols = [request.symbol] if request.symbol else None
    
    try:
        result = backtest_portfolio(
            request.strategy,
            symbols,
            start_date=request.start_date,
            end_date=request.end_date
        )
        
        if 'error' in result:
            raise HTTPException(status_code=400, detail=result['error'])
        
        return {
            "strategy": request.strategy,
            "period": f"{request.start_date} to {request.end_date}",
            "symbolCount": result.get('symbolCount', 0),
            "totalTrades": result.get('totalTrades', 0),
            "winRate": result.get('overallWinRate', 0),
            "expectancy": result.get('avgExpectancy', 0),
            "maxDrawdown": result.get('avgMaxDrawdown', 0),
            "symbols": result.get('symbols', []),
        }
        
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== Portfolio Tracker Endpoints =====

class TradeRequest(BaseModel):
    symbol: str = Field(..., min_length=2, max_length=20, description="Stock symbol")
    entryDate: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD")
    entryPrice: float = Field(..., gt=0, le=1000000, description="Entry price")
    quantity: int = Field(..., ge=1, le=1000000, description="Number of shares")
    stopLoss: float = Field(..., gt=0, le=1000000, description="Stop loss price")
    target: float = Field(..., gt=0, le=1000000, description="Target price")
    signalId: Optional[str] = ""
    notes: Optional[str] = ""
    
    @field_validator('symbol')
    @classmethod
    def validate_symbol_format(cls, v: str) -> str:
        """Ensure symbol is uppercase and alphanumeric"""
        v = v.upper().strip()
        if not re.match(r'^[A-Z0-9&-]+$', v):
            raise ValueError('Symbol must contain only letters, numbers, & or -')
        return v
    
    @model_validator(mode='after')
    def validate_trade_logic(self):
        """Validate SL < entry < target for long trades"""
        if self.stopLoss >= self.entryPrice:
            raise ValueError('Stop loss must be below entry price for long trades')
        if self.target <= self.entryPrice:
            raise ValueError('Target must be above entry price for long trades')
        return self


class TradeUpdateRequest(BaseModel):
    stopLoss: Optional[float] = Field(None, gt=0, le=1000000)
    target: Optional[float] = Field(None, gt=0, le=1000000)
    quantity: Optional[int] = Field(None, ge=1, le=1000000)
    notes: Optional[str] = None


class CloseTradeRequest(BaseModel):
    exitPrice: float = Field(..., gt=0, le=1000000, description="Exit price")
    exitDate: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")


@router.post("/trades")
async def add_trade(request: TradeRequest):
    """Add a new trade to portfolio"""
    from app.data.portfolio import add_trade, Trade
    
    trade = Trade(
        symbol=request.symbol.upper(),
        entry_date=request.entryDate,
        entry_price=request.entryPrice,
        quantity=request.quantity,
        stop_loss=request.stopLoss,
        target=request.target,
        signal_id=request.signalId or "",
        notes=request.notes or "",
    )
    
    result = add_trade(trade)
    return {"success": True, "trade": result.to_dict()}


@router.get("/trades")
async def list_trades(status: Optional[str] = Query(None, description="OPEN or CLOSED")):
    """List all trades, optionally filtered by status"""
    from app.data.portfolio import get_trades
    
    trades = get_trades(status.upper() if status else None)
    return {"trades": [t.to_dict() for t in trades], "count": len(trades)}


@router.get("/trades/{trade_id}")
async def get_trade(trade_id: str):
    """Get single trade by ID"""
    from app.data.portfolio import get_trade_by_id
    
    trade = get_trade_by_id(trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    
    return trade.to_dict()


@router.put("/trades/{trade_id}")
async def update_trade_endpoint(trade_id: str, request: TradeUpdateRequest):
    """Update trade fields (SL, Target, Notes)"""
    from app.data.portfolio import update_trade, get_trade_by_id
    
    trade = get_trade_by_id(trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    
    updates = {}
    if request.stopLoss is not None:
        updates["stop_loss"] = request.stopLoss
    if request.target is not None:
        updates["target"] = request.target
    if request.quantity is not None:
        updates["quantity"] = request.quantity
    if request.notes is not None:
        updates["notes"] = request.notes
    
    result = update_trade(trade_id, updates)
    return {"success": True, "trade": result.to_dict()}


@router.post("/trades/{trade_id}/close")
async def close_trade_endpoint(trade_id: str, request: CloseTradeRequest):
    """Close a trade with exit price"""
    from app.data.portfolio import close_trade, get_trade_by_id
    
    trade = get_trade_by_id(trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    
    result = close_trade(trade_id, request.exitPrice, request.exitDate)
    return {"success": True, "trade": result.to_dict()}


@router.delete("/trades/{trade_id}")
async def delete_trade_endpoint(trade_id: str):
    """Delete a trade"""
    from app.data.portfolio import delete_trade
    
    success = delete_trade(trade_id)
    if not success:
        raise HTTPException(status_code=404, detail="Trade not found")
    
    return {"success": True, "message": "Trade deleted"}


@router.get("/portfolio/stats")
async def get_portfolio_stats_endpoint():
    """Get portfolio summary statistics"""
    from app.data.portfolio import get_portfolio_stats
    
    return get_portfolio_stats()


# ===== Audit & Compliance Endpoints (V2.0) =====

@router.get("/audit/verify")
async def verify_audit_trail(
    date: str = Query(..., description="Date to verify (YYYY-MM-DD)")
):
    """
    Verify hash chain integrity for a specific date's audit log.
    
    Returns:
        - isValid: bool - Whether the chain is intact
        - errors: list - Any integrity violations found
    """
    from datetime import datetime as dt
    from pathlib import Path
    from app.core.audit import verify_audit_chain, AuditLogger
    
    try:
        target_date = dt.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    logger_instance = AuditLogger()
    log_file = logger_instance._get_log_file(target_date)
    
    is_valid, errors = verify_audit_chain(log_file)
    
    return {
        "date": date,
        "logFile": str(log_file),
        "fileExists": log_file.exists(),
        "isValid": is_valid,
        "errors": errors[:10],  # Limit to first 10 errors
        "errorCount": len(errors),
    }


@router.get("/audit/compliance-report")
async def get_compliance_report_endpoint(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)")
):
    """
    Generate compliance report for a date range.
    
    Returns summary statistics and chain verification status for each day.
    Required for SEBI regulatory submissions.
    """
    from datetime import datetime as dt
    from app.core.audit import get_compliance_report
    
    try:
        start = dt.strptime(start_date, "%Y-%m-%d").date()
        end = dt.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    if end < start:
        raise HTTPException(status_code=400, detail="end_date must be >= start_date")
    
    if (end - start).days > 365:
        raise HTTPException(status_code=400, detail="Date range cannot exceed 365 days")
    
    return get_compliance_report(start, end)


@router.get("/audit/portfolio-risk-status")
async def get_portfolio_risk_status():
    """
    Get current portfolio risk manager status.
    
    Includes:
    - Kill switch states (daily/weekly/circuit breaker)
    - Consecutive losses
    - Sector concentration
    - Current regime multiplier
    """
    from app.engine.portfolio_risk import portfolio_risk
    
    return portfolio_risk.get_status()


@router.post("/audit/reset-circuit-breaker")
async def reset_circuit_breaker():
    """
    Manually reset the circuit breaker after review.
    
    ⚠️ Use with caution - this re-enables trading after 3+ consecutive losses.
    """
    from app.engine.portfolio_risk import portfolio_risk
    from app.core.audit import audit_logger
    
    # Log the manual reset for compliance
    audit_logger.log_event("CIRCUIT_BREAKER_RESET", {
        "previousConsecutiveLosses": portfolio_risk.state.consecutive_losses,
        "resetBy": "API"
    })
    
    portfolio_risk.reset_circuit_breaker()
    
    return {
        "success": True,
        "message": "Circuit breaker reset",
        "status": portfolio_risk.get_status()
    }

