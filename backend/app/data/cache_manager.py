"""
TradeEdge Pro - Cache Manager
Redis primary, CSV fallback
"""
import gzip
import pickle
import json
from pathlib import Path
from typing import Optional, Any
from datetime import datetime, timedelta
import pandas as pd

from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

# Try Redis import
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis not available, using CSV fallback only")


class CacheManager:
    """Hybrid cache: Redis primary, CSV fallback"""
    
    def __init__(self):
        self.redis_client = None
        self.cache_dir = Path("data_cache")
        self.cache_dir.mkdir(exist_ok=True)
        
        if REDIS_AVAILABLE:
            try:
                self.redis_client = redis.from_url(
                    settings.redis_url,
                    decode_responses=False
                )
                self.redis_client.ping()
                logger.info("Redis connected successfully")
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}, using CSV fallback")
                self.redis_client = None
    
    def _get_cache_path(self, key: str) -> Path:
        """Get CSV cache file path"""
        safe_key = key.replace(":", "_").replace("/", "_")
        return self.cache_dir / f"{safe_key}.pkl.gz"
    
    def _serialize(self, data: Any) -> bytes:
        """Serialize data with compression"""
        return gzip.compress(pickle.dumps(data))
    
    def _deserialize(self, data: bytes) -> Any:
        """Deserialize compressed data"""
        return pickle.loads(gzip.decompress(data))
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached data"""
        # Try Redis first
        if self.redis_client:
            try:
                data = self.redis_client.get(key)
                if data:
                    logger.debug(f"Cache hit (Redis): {key}")
                    return self._deserialize(data)
            except Exception as e:
                logger.warning(f"Redis get failed: {e}")
        
        # Fallback to CSV
        cache_path = self._get_cache_path(key)
        if cache_path.exists():
            try:
                with open(cache_path, "rb") as f:
                    cached = self._deserialize(f.read())
                
                # Check expiry
                if cached.get("expires_at", datetime.max) > datetime.now():
                    logger.debug(f"Cache hit (CSV): {key}")
                    return cached.get("data")
                else:
                    cache_path.unlink()  # Remove expired
            except Exception as e:
                logger.warning(f"CSV cache read failed: {e}")
        
        logger.debug(f"Cache miss: {key}")
        return None
    
    def set(self, key: str, data: Any, ttl_seconds: int = None) -> bool:
        """Set cached data with TTL"""
        if ttl_seconds is None:
            ttl_seconds = settings.cache_daily_ttl
        
        serialized = self._serialize(data)
        
        # Try Redis first
        if self.redis_client:
            try:
                self.redis_client.setex(key, ttl_seconds, serialized)
                logger.debug(f"Cached to Redis: {key} (TTL: {ttl_seconds}s)")
                return True
            except Exception as e:
                logger.warning(f"Redis set failed: {e}")
        
        # Fallback to CSV
        try:
            cache_path = self._get_cache_path(key)
            cached = {
                "data": data,
                "expires_at": datetime.now() + timedelta(seconds=ttl_seconds),
                "created_at": datetime.now(),
            }
            with open(cache_path, "wb") as f:
                f.write(self._serialize(cached))
            logger.debug(f"Cached to CSV: {key}")
            return True
        except Exception as e:
            logger.error(f"CSV cache write failed: {e}")
            return False
    
    def invalidate(self, key: str) -> bool:
        """Invalidate cache entry"""
        success = False
        
        if self.redis_client:
            try:
                self.redis_client.delete(key)
                success = True
            except Exception:
                pass
        
        cache_path = self._get_cache_path(key)
        if cache_path.exists():
            cache_path.unlink()
            success = True
        
        return success
    
    def get_stats(self) -> dict:
        """Get cache statistics"""
        stats = {
            "redis_available": self.redis_client is not None,
            "csv_files": len(list(self.cache_dir.glob("*.pkl.gz"))),
        }
        
        if self.redis_client:
            try:
                info = self.redis_client.info("memory")
                stats["redis_memory_used"] = info.get("used_memory_human", "N/A")
            except Exception:
                pass
        
        return stats


# Global cache instance
cache = CacheManager()


def get_daily_cache_key(symbol: str) -> str:
    """Generate cache key for daily data"""
    return f"daily:{symbol}:{datetime.now().strftime('%Y-%m-%d')}"


def get_intraday_cache_key(symbol: str) -> str:
    """Generate cache key for intraday data"""
    return f"intraday:{symbol}:{datetime.now().strftime('%Y-%m-%d-%H')}"
