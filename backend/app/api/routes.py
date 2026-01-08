"""
TradeEdge Pro - Enhanced API Routes
With score breakdown and risk snapshot
"""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
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
    capital: float = 100000
    risk_percent: float = 1.0
    entry: float
    stop_loss: float


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


@router.get("/intraday-bias", response_model=List[SignalResponse])
async def get_intraday_bias_signals(
    limit: int = Query(10, ge=1, le=50),
    sector: Optional[str] = Query(None),
):
    """
    Get intraday bias signals with score breakdown.
    Uses NIFTY trend for market regime filter.
    """
    logger.info(f"Fetching intraday-bias signals (limit={limit})")
    
    results = generate_signals(
        strategy_type="intraday_bias",
        market_regime="neutral",
        max_signals=limit,
    )
    
    # Filter by sector
    if sector:
        results = [r for r in results if r.get("sector", "").lower() == sector.lower()]
    
    # Convert to response
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


# ===== Portfolio Tracker Endpoints =====

class TradeRequest(BaseModel):
    symbol: str
    entryDate: str
    entryPrice: float
    quantity: int
    stopLoss: float
    target: float
    signalId: Optional[str] = ""
    notes: Optional[str] = ""


class TradeUpdateRequest(BaseModel):
    stopLoss: Optional[float] = None
    target: Optional[float] = None
    quantity: Optional[int] = None
    notes: Optional[str] = None


class CloseTradeRequest(BaseModel):
    exitPrice: float
    exitDate: Optional[str] = None


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



