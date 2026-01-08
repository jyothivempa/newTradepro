"""
TradeEdge Pro - NSE Calendar
Handles market holidays and trading hours for graceful scan skipping.
"""
from datetime import datetime, date
from typing import Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)


# NSE Holidays 2026 (Update annually)
NSE_HOLIDAYS_2026 = [
    "2026-01-26",  # Republic Day
    "2026-03-10",  # Maha Shivaratri
    "2026-03-17",  # Holi
    "2026-04-02",  # Ram Navami
    "2026-04-03",  # Good Friday
    "2026-04-14",  # Ambedkar Jayanti
    "2026-04-21",  # Mahavir Jayanti
    "2026-05-01",  # May Day
    "2026-05-25",  # Buddha Purnima
    "2026-07-17",  # Muharram
    "2026-08-15",  # Independence Day
    "2026-09-16",  # Milad-un-Nabi
    "2026-10-02",  # Gandhi Jayanti
    "2026-10-20",  # Dussehra
    "2026-11-09",  # Diwali (Laxmi Puja)
    "2026-11-10",  # Diwali Balipratipada
    "2026-11-30",  # Guru Nanak Jayanti
    "2026-12-25",  # Christmas
]

# Also add 2025 for testing
NSE_HOLIDAYS_2025 = [
    "2025-01-26",  # Republic Day
    "2025-02-26",  # Maha Shivaratri
    "2025-03-14",  # Holi
    "2025-03-31",  # Id-ul-Fitr
    "2025-04-10",  # Mahavir Jayanti/Ram Navami
    "2025-04-14",  # Ambedkar Jayanti
    "2025-04-18",  # Good Friday
    "2025-05-01",  # May Day
    "2025-05-12",  # Buddha Purnima
    "2025-06-07",  # Id-ul-Zuha (Bakrid)
    "2025-08-15",  # Independence Day
    "2025-08-27",  # Janmashtami
    "2025-10-02",  # Gandhi Jayanti/Dussehra
    "2025-10-21",  # Diwali Laxmi Pujan
    "2025-10-22",  # Diwali Balipratipada
    "2025-11-05",  # Guru Nanak Jayanti
    "2025-12-25",  # Christmas
]

ALL_HOLIDAYS = set(NSE_HOLIDAYS_2025 + NSE_HOLIDAYS_2026)


def is_nse_holiday(check_date: Optional[str] = None) -> bool:
    """
    Check if the given date is an NSE holiday.
    
    Args:
        check_date: Date in YYYY-MM-DD format. Defaults to today.
        
    Returns:
        True if NSE is closed
    """
    if check_date is None:
        check_date = date.today().isoformat()
    
    return check_date in ALL_HOLIDAYS


def is_weekend(check_date: Optional[str] = None) -> bool:
    """Check if date is Saturday or Sunday"""
    if check_date is None:
        d = date.today()
    else:
        d = datetime.strptime(check_date, "%Y-%m-%d").date()
    
    return d.weekday() >= 5  # 5=Saturday, 6=Sunday


def is_market_open(check_date: Optional[str] = None) -> bool:
    """
    Check if NSE market is open on the given date.
    
    Returns:
        True if market is open (not weekend and not holiday)
    """
    if check_date is None:
        check_date = date.today().isoformat()
    
    if is_weekend(check_date):
        return False
    
    if is_nse_holiday(check_date):
        return False
    
    return True


def should_skip_scan() -> tuple[bool, str]:
    """
    Check if signal scan should be skipped today.
    
    Returns:
        (should_skip, reason)
    """
    today = date.today().isoformat()
    
    if is_weekend(today):
        return True, "Weekend - market closed"
    
    if is_nse_holiday(today):
        return True, f"NSE Holiday - {today}"
    
    return False, ""


def get_next_trading_day(from_date: Optional[str] = None) -> str:
    """Get the next trading day from given date"""
    from datetime import timedelta
    
    if from_date is None:
        d = date.today()
    else:
        d = datetime.strptime(from_date, "%Y-%m-%d").date()
    
    d += timedelta(days=1)
    
    while not is_market_open(d.isoformat()):
        d += timedelta(days=1)
    
    return d.isoformat()
