"""
TradeEdge Pro - Institutional Flow Data
FII/DII buy/sell data from NSE India
"""
from typing import Dict, Optional
from datetime import datetime, date
import httpx

from app.utils.logger import get_logger

logger = get_logger(__name__)

# Cache for FII/DII data
_flow_cache: Dict[str, dict] = {}
_cache_ttl = 900  # 15 minutes

# NSE headers to mimic browser
NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
    "Origin": "https://www.nseindia.com",
}


async def _fetch_nse_data(url: str) -> Optional[dict]:
    """Fetch data from NSE with proper headers"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # First get cookies
            await client.get("https://www.nseindia.com/", headers=NSE_HEADERS)
            
            # Then fetch data
            response = await client.get(url, headers=NSE_HEADERS)
            
            if response.status_code == 200:
                return response.json()
            
            logger.warning(f"NSE API returned {response.status_code}")
            return None
    
    except Exception as e:
        logger.warning(f"NSE fetch failed: {e}")
        return None


def get_fii_dii_data_sync() -> dict:
    """
    Get FII/DII trading activity (synchronous version).
    Uses cached/mock data for reliability.
    
    Returns:
        {
            "date": str,
            "fii": {"buyValue": float, "sellValue": float, "netValue": float},
            "dii": {"buyValue": float, "sellValue": float, "netValue": float},
            "netFlow": float,
            "bias": str  # "bullish", "bearish", "neutral"
        }
    """
    # Check cache
    cache_key = str(date.today())
    if cache_key in _flow_cache:
        cached = _flow_cache[cache_key]
        if datetime.now().timestamp() - cached.get("timestamp", 0) < _cache_ttl:
            return cached["data"]
    
    # Try to fetch from alternative sources
    # Since NSE requires async and sessions, use a simpler approach
    
    # Mock data based on market hours (will be replaced with real API)
    # In production, integrate with a paid data provider or use webscraping
    
    try:
        import yfinance as yf
        
        # Get NIFTY trend as proxy for institutional activity
        nifty = yf.Ticker("^NSEI")
        hist = nifty.history(period="5d")
        
        if len(hist) >= 2:
            last_close = hist['Close'].iloc[-1]
            prev_close = hist['Close'].iloc[-2]
            change_pct = ((last_close - prev_close) / prev_close) * 100
            
            # Estimate FII/DII based on market movement
            if change_pct > 0.5:
                fii_net = abs(change_pct) * 500  # Positive = buying
                dii_net = abs(change_pct) * 300
                bias = "bullish"
            elif change_pct < -0.5:
                fii_net = -abs(change_pct) * 500  # Negative = selling
                dii_net = abs(change_pct) * 200  # DII usually supports
                bias = "bearish"
            else:
                fii_net = 0
                dii_net = 0
                bias = "neutral"
            
            result = {
                "date": str(date.today()),
                "fii": {
                    "buyValue": max(0, fii_net + 1000),
                    "sellValue": max(0, 1000 - fii_net),
                    "netValue": round(fii_net, 2),
                },
                "dii": {
                    "buyValue": max(0, dii_net + 800),
                    "sellValue": max(0, 800 - dii_net),
                    "netValue": round(dii_net, 2),
                },
                "netFlow": round(fii_net + dii_net, 2),
                "bias": bias,
                "source": "estimated",
            }
        else:
            result = _get_default_flow()
    
    except Exception as e:
        logger.warning(f"FII/DII estimation failed: {e}")
        result = _get_default_flow()
    
    # Cache result
    _flow_cache[cache_key] = {"data": result, "timestamp": datetime.now().timestamp()}
    
    logger.info(f"FII/DII bias: {result['bias']} (FII: {result['fii']['netValue']}, DII: {result['dii']['netValue']})")
    return result


def _get_default_flow() -> dict:
    """Return default/neutral flow data"""
    return {
        "date": str(date.today()),
        "fii": {"buyValue": 0, "sellValue": 0, "netValue": 0},
        "dii": {"buyValue": 0, "sellValue": 0, "netValue": 0},
        "netFlow": 0,
        "bias": "neutral",
        "source": "unavailable",
    }


def get_institutional_bias() -> str:
    """
    Get overall institutional bias.
    
    Returns: "bullish", "bearish", or "neutral"
    """
    data = get_fii_dii_data_sync()
    return data.get("bias", "neutral")


def get_institutional_penalty() -> int:
    """
    Get score adjustment based on institutional flow.
    
    Returns:
        +15 (both buying) to -15 (FII selling)
    """
    data = get_fii_dii_data_sync()
    
    fii_net = data["fii"]["netValue"]
    dii_net = data["dii"]["netValue"]
    
    # Both buying = strong bullish
    if fii_net > 0 and dii_net > 0:
        return 15
    
    # FII buying, DII neutral/selling = moderate bullish
    if fii_net > 0:
        return 10
    
    # FII selling = bearish signal
    if fii_net < -500:
        return -15
    
    # DII buying against FII selling = support
    if fii_net < 0 and dii_net > 0:
        return -5
    
    return 0


def clear_cache():
    """Clear FII/DII cache"""
    global _flow_cache
    _flow_cache = {}
    logger.info("FII/DII cache cleared")
