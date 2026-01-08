"""
TradeEdge Pro - Sector Benchmarks
Sector-specific thresholds for volume, ATR, and other metrics.
"""
from typing import Dict

# Sector-relative volume medians
# Higher values = sector typically has more trading activity
SECTOR_VOLUME_MEDIAN: Dict[str, float] = {
    "BANK": 2.0,          # High trading activity
    "PSU BANK": 2.2,      # Very active
    "PRIVATE BANK": 2.0,
    "METAL": 2.5,         # Very active, volatile
    "IT": 1.3,            # Moderate
    "PHARMA": 1.2,
    "AUTO": 1.5,
    "FMCG": 1.2,          # Defensive, lower volume
    "ENERGY": 1.8,
    "INFRA": 1.6,
    "REALTY": 2.0,        # Speculative
    "MEDIA": 1.4,
    "TELECOM": 1.5,
    "CEMENT": 1.5,
    "CHEMICAL": 1.4,
    "DEFAULT": 1.5,
}

# Sector-specific ATR percentage caps
# Higher values = sector is inherently more volatile
SECTOR_ATR_CAPS: Dict[str, float] = {
    "BANK": 2.5,
    "PSU BANK": 3.0,      # Very volatile
    "PRIVATE BANK": 2.5,
    "METAL": 3.0,         # Commodity-linked, high vol
    "IT": 2.0,            # Generally stable
    "PHARMA": 2.2,
    "AUTO": 2.5,
    "FMCG": 2.0,          # Defensive
    "ENERGY": 2.8,
    "INFRA": 2.5,
    "REALTY": 3.0,        # High volatility
    "MEDIA": 2.5,
    "TELECOM": 2.5,
    "CEMENT": 2.5,
    "CHEMICAL": 2.5,
    "DEFAULT": 2.2,
}

# Minimum ATR % (below = DEAD market for that sector)
SECTOR_ATR_MINS: Dict[str, float] = {
    "BANK": 0.3,
    "IT": 0.2,
    "FMCG": 0.15,
    "METAL": 0.5,
    "DEFAULT": 0.25,
}


def get_sector_atr_cap(sector: str) -> float:
    """Get ATR cap for a sector (max allowed ATR %)"""
    if not sector:
        return SECTOR_ATR_CAPS["DEFAULT"]
    sector_upper = sector.upper()
    return SECTOR_ATR_CAPS.get(sector_upper, SECTOR_ATR_CAPS["DEFAULT"])


def get_sector_atr_min(sector: str) -> float:
    """Get ATR minimum for a sector (below = market DEAD)"""
    if not sector:
        return SECTOR_ATR_MINS["DEFAULT"]
    sector_upper = sector.upper()
    return SECTOR_ATR_MINS.get(sector_upper, SECTOR_ATR_MINS["DEFAULT"])


def get_sector_volume_median(sector: str) -> float:
    """Get volume median for sector-relative volume calculation"""
    if not sector:
        return SECTOR_VOLUME_MEDIAN["DEFAULT"]
    sector_upper = sector.upper()
    return SECTOR_VOLUME_MEDIAN.get(sector_upper, SECTOR_VOLUME_MEDIAN["DEFAULT"])


def calculate_relative_volume(
    today_volume: float,
    median_volume: float,
    sector: str = ""
) -> float:
    """
    Calculate sector-normalized relative volume.
    
    Returns:
        Volume ratio normalized by sector median.
        > 1.0 = above average for that sector
        < 1.0 = below average
    """
    if median_volume <= 0:
        return 0.0
    
    raw_ratio = today_volume / median_volume
    sector_median = get_sector_volume_median(sector)
    
    # Normalize: If sector typically has 2x volume, raw 2x is just average
    return raw_ratio / sector_median


def is_volume_sufficient(relative_volume: float, threshold: float = 1.0) -> bool:
    """Check if sector-normalized volume is sufficient"""
    return relative_volume >= threshold
