"""
TradeEdge Pro - Data Fetching Module
Yahoo Finance primary, NSE secondary, Alpha Vantage tertiary fallback
With auto-switch logic on repeated failures.
"""
import time
import random
from typing import Optional
import pandas as pd
import yfinance as yf
import httpx
from datetime import datetime, timedelta

from app.config import get_settings
from app.utils.logger import get_logger
from app.data.data_source_monitor import failure_tracker

logger = get_logger(__name__)
settings = get_settings()

# Try NSE library import
try:
    from nsepy import get_history
    NSE_AVAILABLE = True
except ImportError:
    NSE_AVAILABLE = False
    logger.warning("nsepy not installed. NSE fallback unavailable. Install with: pip install nsepy")


class DataFetchError(Exception):
    """Custom exception for data fetch failures"""
    pass


def validate_df(df: pd.DataFrame) -> bool:
    """
    Validate DataFrame integrity before analysis.
    Returns False if data is insufficient or corrupt.
    """
    if df is None or df.empty:
        return False
    
    if len(df) < settings.min_data_points:
        return False
    
    required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
    if not all(col in df.columns for col in required_cols):
        return False
    
    if df[required_cols].isna().any().any():
        return False
    
    if not df.index.is_monotonic_increasing:
        return False
    
    # Check for zero/negative prices
    if (df[['Open', 'High', 'Low', 'Close']] <= 0).any().any():
        return False
    
    return True


def _retry_fetch(func, source_name: str, *args, **kwargs) -> Optional[pd.DataFrame]:
    """Retry wrapper with exponential backoff, jitter, and failure tracking"""
    for attempt in range(settings.max_retry_attempts):
        try:
            result = func(*args, **kwargs)
            if result is not None and not result.empty:
                return result
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"Fetch attempt {attempt + 1} failed ({source_name}): {error_msg}")
            if "Too Many Requests" in error_msg:
                logger.warning("Rate limit detected. Backing off...")
        
        if attempt < settings.max_retry_attempts - 1:
            # Exponential backoff + Random Jitter to prevent thundering herd
            sleep_time = (settings.retry_delay_seconds * (2 ** attempt)) + random.uniform(0, 1)
            time.sleep(sleep_time)
    
    return None


def _fetch_yahoo_daily(symbol: str, period: str = "5y") -> Optional[pd.DataFrame]:
    """Fetch daily data from Yahoo Finance"""
    # Courtesy delay to prevent rate limits in threaded environment
    time.sleep(random.uniform(0.5, 2.0))
    
    ticker = f"{symbol}.NS"
    try:
        df = yf.download(ticker, period=period, progress=False, auto_adjust=True)
        if df.empty:
            return None
        df.columns = df.columns.droplevel(1) if isinstance(df.columns, pd.MultiIndex) else df.columns
        return df
    except Exception as e:
        logger.error(f"Yahoo fetch failed for {symbol}: {e}")
        raise  # Re-raise to let retry handler catch it


def _fetch_yahoo_intraday(symbol: str, interval: str = "15m", period: str = "60d") -> Optional[pd.DataFrame]:
    """Fetch intraday data from Yahoo Finance"""
    time.sleep(random.uniform(0.5, 2.0))
    
    ticker = f"{symbol}.NS"
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False)
        if df.empty:
            return None
        df.columns = df.columns.droplevel(1) if isinstance(df.columns, pd.MultiIndex) else df.columns
        return df
    except Exception as e:
        logger.error(f"Yahoo intraday fetch failed for {symbol}: {e}")
        raise


def _fetch_nse_daily(symbol: str, years: int = 5) -> Optional[pd.DataFrame]:
    """Secondary fallback: Fetch daily data from NSE via nsepy"""
    if not NSE_AVAILABLE:
        return None
    
    try:
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=years * 365)
        
        # nsepy uses symbol without exchange suffix
        df = get_history(symbol=symbol, start=start_date, end=end_date)
        
        if df.empty:
            return None
        
        # Rename columns to match expected format
        df = df.rename(columns={
            "Open": "Open",
            "High": "High", 
            "Low": "Low",
            "Close": "Close",
            "Volume": "Volume",
        })
        
        # Keep only required columns
        df = df[["Open", "High", "Low", "Close", "Volume"]]
        
        return df
    except Exception as e:
        logger.error(f"NSE fetch failed for {symbol}: {e}")
        raise


def _fetch_alpha_vantage_daily(symbol: str) -> Optional[pd.DataFrame]:
    """Tertiary fallback: Fetch daily data from Alpha Vantage"""
    if not settings.alpha_vantage_key:
        return None
    
    try:
        url = "https://www.alphavantage.co/query"
        params = {
            "function": "TIME_SERIES_DAILY_ADJUSTED",
            "symbol": f"{symbol}.NSE",
            "outputsize": "full",
            "apikey": settings.alpha_vantage_key,
        }
        
        response = httpx.get(url, params=params, timeout=30)
        data = response.json()
        
        if "Time Series (Daily)" not in data:
            return None
        
        ts = data["Time Series (Daily)"]
        df = pd.DataFrame.from_dict(ts, orient="index")
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        
        # Rename columns
        df.columns = ["Open", "High", "Low", "Close", "Adj Close", "Volume", "Dividend", "Split"]
        df = df[["Open", "High", "Low", "Close", "Volume"]].astype(float)
        
        return df
    except Exception as e:
        logger.error(f"Alpha Vantage fetch failed for {symbol}: {e}")
        raise


def fetch_daily_data(symbol: str, period: str = "5y") -> Optional[pd.DataFrame]:
    """
    Fetch daily OHLCV data with intelligent fallback and failure tracking.
    
    Priority:
    1. Yahoo Finance (primary)
    2. NSE via nsepy (secondary)
    3. Alpha Vantage (tertiary)
    
    Auto-switches when a source fails >2x consecutively in a sync job.
    """
    df = None
    
    # --- Try Yahoo Finance (Primary) ---
    if not failure_tracker.should_skip_source("yahoo"):
        try:
            df = _retry_fetch(_fetch_yahoo_daily, "yahoo", symbol, period)
            if df is not None and validate_df(df):
                failure_tracker.record_success("yahoo")
                logger.info(f"Fetched {symbol} from Yahoo ({len(df)} bars)")
                return df
            else:
                failure_tracker.record_failure("yahoo", f"Invalid data for {symbol}")
        except Exception as e:
            failure_tracker.record_failure("yahoo", str(e))
    else:
        logger.debug(f"Skipping Yahoo for {symbol} (degraded)")
    
    # --- Try NSE (Secondary) ---
    if NSE_AVAILABLE and not failure_tracker.should_skip_source("nse"):
        try:
            # Convert period to years for NSE
            years = 5 if "y" in period else 1
            df = _retry_fetch(_fetch_nse_daily, "nse", symbol, years)
            if df is not None and validate_df(df):
                failure_tracker.record_success("nse")
                logger.info(f"Fetched {symbol} from NSE ({len(df)} bars)")
                return df
            else:
                failure_tracker.record_failure("nse", f"Invalid data for {symbol}")
        except Exception as e:
            failure_tracker.record_failure("nse", str(e))
    else:
        if not NSE_AVAILABLE:
            logger.debug(f"NSE unavailable for {symbol}")
        else:
            logger.debug(f"Skipping NSE for {symbol} (degraded)")
    
    # --- Try Alpha Vantage (Tertiary) ---
    if not failure_tracker.should_skip_source("alpha_vantage"):
        try:
            df = _retry_fetch(_fetch_alpha_vantage_daily, "alpha_vantage", symbol)
            if df is not None and validate_df(df):
                failure_tracker.record_success("alpha_vantage")
                logger.info(f"Fetched {symbol} from Alpha Vantage ({len(df)} bars)")
                return df
            else:
                failure_tracker.record_failure("alpha_vantage", f"Invalid data for {symbol}")
        except Exception as e:
            failure_tracker.record_failure("alpha_vantage", str(e))
    else:
        logger.debug(f"Skipping Alpha Vantage for {symbol} (degraded)")
    
    # All sources failed
    logger.error(f"All data sources failed for {symbol}")
    return None


def fetch_intraday_data(symbol: str, interval: str = "15m", period: str = "60d") -> Optional[pd.DataFrame]:
    """
    Fetch intraday OHLCV data.
    Note: Yahoo limits intraday data to ~60 days. NSE doesn't provide intraday via nsepy.
    """
    if not failure_tracker.should_skip_source("yahoo"):
        try:
            df = _retry_fetch(_fetch_yahoo_intraday, "yahoo", symbol, interval, period)
            if df is not None and validate_df(df):
                failure_tracker.record_success("yahoo")
                logger.info(f"Fetched intraday data for {symbol} ({len(df)} bars)")
                return df
            failure_tracker.record_failure("yahoo", f"Invalid intraday data for {symbol}")
        except Exception as e:
            failure_tracker.record_failure("yahoo", str(e))
    
    logger.error(f"Intraday fetch failed for {symbol}")
    return None


def fetch_nifty_index() -> Optional[pd.DataFrame]:
    """Fetch NIFTY 50 index data for market regime detection"""
    return fetch_daily_data("^NSEI".replace(".NS", ""), period="1y")


def get_data_source_status() -> dict:
    """Get current status of all data sources"""
    return failure_tracker.get_full_status()

