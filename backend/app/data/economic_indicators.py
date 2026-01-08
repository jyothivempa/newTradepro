"""
TradeEdge Pro - Economic Indicators
Fetches RBI rates and economic data for regime enhancement.

Optional feature - disabled by default via config.py
"""
import httpx
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from functools import lru_cache

from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

# Cache for 24 hours (rates don't change frequently)
_economic_cache = {"data": None, "timestamp": None}
CACHE_TTL_HOURS = 24


@dataclass
class EconomicContext:
    """Economic indicators for regime enhancement"""
    repo_rate: float  # RBI repo rate %
    cpi_inflation: float  # CPI YoY %
    rate_bias: str  # "hawkish", "neutral", "dovish"
    gdp_growth: float  # GDP growth %
    last_updated: datetime
    source: str  # Data source
    
    def to_dict(self) -> dict:
        return {
            "repoRate": self.repo_rate,
            "cpiInflation": self.cpi_inflation,
            "rateBias": self.rate_bias,
            "gdpGrowth": self.gdp_growth,
            "lastUpdated": self.last_updated.isoformat(),
            "source": self.source,
        }


def _determine_rate_bias(repo_rate: float, cpi_inflation: float) -> str:
    """
    Determine RBI's likely monetary policy bias.
    
    Logic:
    - Hawkish: High inflation (CPI > 6%) or recent rate hikes
    - Dovish: Low inflation (CPI < 4%) or accommodative stance
    - Neutral: Otherwise
    """
    # RBI's inflation target is 4% (+/- 2%)
    if cpi_inflation > 6.0:
        return "hawkish"  # High inflation = likely to raise rates
    elif cpi_inflation < 4.0 and repo_rate > 5.0:
        return "dovish"  # Low inflation with room to cut
    else:
        return "neutral"


def get_rbi_data() -> Optional[EconomicContext]:
    """
    Fetch RBI repo rate and inflation data.
    Uses cached data if available and fresh.
    
    Note: In production, you'd scrape from RBI website or use a data API.
    For now, we use reasonable defaults that can be overridden.
    """
    global _economic_cache
    
    if not settings.enable_economic_indicators:
        return None
    
    # Check cache
    if _economic_cache["timestamp"]:
        age = datetime.now() - _economic_cache["timestamp"]
        if age < timedelta(hours=CACHE_TTL_HOURS):
            return _economic_cache["data"]
    
    try:
        # Try to fetch from a public API or scrape RBI
        # For reliability, we use sensible defaults with option to override
        context = _fetch_from_source()
        
        if context:
            _economic_cache = {"data": context, "timestamp": datetime.now()}
            return context
            
    except Exception as e:
        logger.warning(f"Failed to fetch economic data: {e}")
    
    # Return cached data if available, else defaults
    if _economic_cache["data"]:
        return _economic_cache["data"]
    
    return _get_default_economic_context()


def _fetch_from_source() -> Optional[EconomicContext]:
    """
    Attempt to fetch live economic data.
    
    Sources to try:
    1. RBI website (scraping)
    2. MOSPI for CPI
    3. Public APIs
    """
    try:
        # Example: Fetch from a JSON API (you'd replace with actual source)
        # For now, return None to use defaults
        # In production, you'd implement actual scraping here
        
        # Placeholder: Could scrape from:
        # - https://rbi.org.in/scripts/WSSViewDetail.aspx?TYPE=Section&PARAM1=2
        # - https://mospi.gov.in/
        
        return None  # Return None to use defaults for now
        
    except Exception as e:
        logger.debug(f"Source fetch failed: {e}")
        return None


def _get_default_economic_context() -> EconomicContext:
    """
    Return default economic context.
    These values should be periodically updated or overridden via env vars.
    """
    # Current approximate values (Jan 2026)
    repo_rate = 6.50  # RBI repo rate
    cpi_inflation = 5.2  # CPI inflation
    gdp_growth = 6.8  # GDP growth
    
    return EconomicContext(
        repo_rate=repo_rate,
        cpi_inflation=cpi_inflation,
        rate_bias=_determine_rate_bias(repo_rate, cpi_inflation),
        gdp_growth=gdp_growth,
        last_updated=datetime.now(),
        source="default",
    )


def get_economic_bias() -> str:
    """
    Get simple economic bias for regime enhancement.
    
    Returns:
        "hawkish", "neutral", or "dovish"
    """
    context = get_rbi_data()
    if context:
        return context.rate_bias
    return "neutral"


def get_sector_bias(economic_bias: str) -> dict:
    """
    Get sector recommendations based on economic bias.
    
    Returns:
        Dict of sector -> bias (overweight/underweight/neutral)
    """
    if economic_bias == "hawkish":
        # Rising rates: Favor banks, defensives. Avoid rate-sensitives.
        return {
            "Banking": "overweight",
            "FMCG": "overweight",
            "IT": "neutral",
            "Realty": "underweight",
            "Auto": "underweight",
        }
    elif economic_bias == "dovish":
        # Falling rates: Favor rate-sensitives, growth.
        return {
            "Realty": "overweight",
            "Auto": "overweight",
            "Infra": "overweight",
            "Banking": "neutral",
            "FMCG": "neutral",
        }
    else:
        return {}  # Neutral: No specific bias
