"""
TradeEdge Pro - Live Price Quotes
Real-time/near-real-time price data from NSE
"""
from typing import Dict, List, Optional
from datetime import datetime
import yfinance as yf

from app.utils.logger import get_logger

logger = get_logger(__name__)

# Cache for live quotes
_quote_cache: Dict[str, dict] = {}
_cache_ttl = 60  # 1 minute cache


def get_live_price(symbol: str) -> dict:
    """
    Get live/delayed price for a single stock.
    
    Returns:
        {
            "symbol": str,
            "ltp": float,  # Last traded price
            "change": float,  # Price change
            "changePct": float,  # Percentage change
            "open": float,
            "high": float,
            "low": float,
            "volume": int,
            "timestamp": str,
            "delay": str  # "live" or "15min delayed"
        }
    """
    # Check cache
    cache_key = symbol
    if cache_key in _quote_cache:
        cached = _quote_cache[cache_key]
        if datetime.now().timestamp() - cached.get("timestamp", 0) < _cache_ttl:
            return cached["data"]
    
    try:
        # Use yfinance for price data
        ticker_symbol = f"{symbol}.NS"  # NSE suffix
        ticker = yf.Ticker(ticker_symbol)
        
        # Get intraday data for today
        hist = ticker.history(period="1d", interval="1m")
        
        if hist.empty:
            # Fallback to daily data
            hist = ticker.history(period="5d")
            if hist.empty:
                return _get_empty_quote(symbol)
        
        latest = hist.iloc[-1]
        first = hist.iloc[0]
        
        ltp = float(latest['Close'])
        open_price = float(first['Open'])
        change = ltp - open_price
        change_pct = (change / open_price) * 100 if open_price > 0 else 0
        
        result = {
            "symbol": symbol,
            "ltp": round(ltp, 2),
            "change": round(change, 2),
            "changePct": round(change_pct, 2),
            "open": round(open_price, 2),
            "high": round(float(hist['High'].max()), 2),
            "low": round(float(hist['Low'].min()), 2),
            "volume": int(hist['Volume'].sum()),
            "timestamp": datetime.now().isoformat(),
            "delay": "15min delayed",  # yfinance has 15-20 min delay
        }
        
        # Cache result
        _quote_cache[cache_key] = {"data": result, "timestamp": datetime.now().timestamp()}
        
        return result
    
    except Exception as e:
        logger.warning(f"Failed to get live price for {symbol}: {e}")
        return _get_empty_quote(symbol)


def get_live_prices(symbols: List[str]) -> List[dict]:
    """Get live prices for multiple stocks"""
    results = []
    
    for symbol in symbols[:20]:  # Limit to 20 to avoid rate limits
        try:
            quote = get_live_price(symbol)
            results.append(quote)
        except Exception as e:
            logger.warning(f"Failed to get price for {symbol}: {e}")
            results.append(_get_empty_quote(symbol))
    
    return results


def get_bulk_quotes(symbols: List[str]) -> Dict[str, dict]:
    """
    Get bulk quotes using yfinance download.
    More efficient for multiple symbols.
    """
    try:
        # Convert to NSE format
        tickers = [f"{s}.NS" for s in symbols[:50]]
        
        # Bulk download
        data = yf.download(
            tickers,
            period="1d",
            interval="1m",
            progress=False,
            group_by="ticker",
        )
        
        if data.empty:
            return {}
        
        results = {}
        
        for symbol in symbols:
            ticker = f"{symbol}.NS"
            try:
                if ticker in data.columns.get_level_values(0):
                    ticker_data = data[ticker]
                    if not ticker_data.empty:
                        latest = ticker_data.iloc[-1]
                        first = ticker_data.iloc[0]
                        
                        ltp = float(latest['Close'])
                        open_price = float(first['Open'])
                        change = ltp - open_price
                        change_pct = (change / open_price) * 100 if open_price > 0 else 0
                        
                        results[symbol] = {
                            "symbol": symbol,
                            "ltp": round(ltp, 2),
                            "change": round(change, 2),
                            "changePct": round(change_pct, 2),
                            "timestamp": datetime.now().isoformat(),
                        }
            except Exception:
                continue
        
        return results
    
    except Exception as e:
        logger.warning(f"Bulk quote fetch failed: {e}")
        return {}


def _get_empty_quote(symbol: str) -> dict:
    """Return empty quote structure"""
    return {
        "symbol": symbol,
        "ltp": 0,
        "change": 0,
        "changePct": 0,
        "open": 0,
        "high": 0,
        "low": 0,
        "volume": 0,
        "timestamp": datetime.now().isoformat(),
        "delay": "unavailable",
    }


def is_market_open() -> bool:
    """Check if NSE market is currently open"""
    now = datetime.now()
    
    # NSE hours: 9:15 AM to 3:30 PM IST, Mon-Fri
    if now.weekday() >= 5:  # Saturday or Sunday
        return False
    
    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    
    return market_open <= now <= market_close


def get_market_status() -> dict:
    """Get current market status"""
    now = datetime.now()
    is_open = is_market_open()
    
    if is_open:
        status = "open"
        message = "Market is open"
    elif now.hour < 9 or (now.hour == 9 and now.minute < 15):
        status = "pre-market"
        message = "Market opens at 9:15 AM"
    elif now.hour >= 15 and now.minute >= 30:
        status = "closed"
        message = "Market closed for today"
    else:
        status = "closed"
        message = "Market is closed"
    
    return {
        "status": status,
        "message": message,
        "timestamp": now.isoformat(),
        "isOpen": is_open,
    }


def clear_cache():
    """Clear quote cache"""
    global _quote_cache
    _quote_cache = {}
    logger.info("Quote cache cleared")
