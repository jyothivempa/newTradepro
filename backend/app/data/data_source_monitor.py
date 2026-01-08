"""
TradeEdge Pro - Data Source Monitor
Tracks data source health and enables auto-switch on failures.
"""
import threading
from enum import Enum
from typing import Dict, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


class DataSourceStatus(Enum):
    """Health status of a data source"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"


@dataclass
class SourceMetrics:
    """Metrics for a single data source"""
    name: str
    consecutive_failures: int = 0
    total_successes: int = 0
    total_failures: int = 0
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    last_error: Optional[str] = None
    status: DataSourceStatus = DataSourceStatus.HEALTHY
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage"""
        total = self.total_successes + self.total_failures
        if total == 0:
            return 100.0
        return (self.total_successes / total) * 100
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API response"""
        return {
            "name": self.name,
            "status": self.status.value,
            "consecutiveFailures": self.consecutive_failures,
            "successRate": round(self.success_rate, 2),
            "totalSuccesses": self.total_successes,
            "totalFailures": self.total_failures,
            "lastSuccess": self.last_success.isoformat() if self.last_success else None,
            "lastFailure": self.last_failure.isoformat() if self.last_failure else None,
            "lastError": self.last_error,
        }


class FailureTracker:
    """
    Thread-safe tracker for data source failures with auto-switch logic.
    
    When a source fails consecutively more than the threshold,
    it's marked as DEGRADED and will be skipped for a cooldown period.
    """
    
    # Default sources to track
    SOURCES = ["yahoo", "nse", "alpha_vantage"]
    
    def __init__(
        self,
        failure_threshold: int = 2,
        recovery_seconds: int = 300,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_seconds = recovery_seconds
        self._lock = threading.Lock()
        self._metrics: Dict[str, SourceMetrics] = {
            name: SourceMetrics(name=name) for name in self.SOURCES
        }
        self._session_failures: Dict[str, int] = {name: 0 for name in self.SOURCES}
    
    def record_success(self, source: str) -> None:
        """Record a successful fetch from a source"""
        with self._lock:
            if source not in self._metrics:
                self._metrics[source] = SourceMetrics(name=source)
            
            m = self._metrics[source]
            m.consecutive_failures = 0
            m.total_successes += 1
            m.last_success = datetime.now()
            m.status = DataSourceStatus.HEALTHY
            
            logger.debug(f"Data source '{source}' success recorded")
    
    def record_failure(self, source: str, error: str = None) -> None:
        """Record a failed fetch from a source"""
        with self._lock:
            if source not in self._metrics:
                self._metrics[source] = SourceMetrics(name=source)
            
            m = self._metrics[source]
            m.consecutive_failures += 1
            m.total_failures += 1
            m.last_failure = datetime.now()
            m.last_error = error
            
            # Track session failures for post-sync summary
            self._session_failures[source] = self._session_failures.get(source, 0) + 1
            
            # Update status based on threshold
            if m.consecutive_failures >= self.failure_threshold:
                was_healthy = m.status == DataSourceStatus.HEALTHY
                m.status = DataSourceStatus.DEGRADED
                logger.warning(
                    f"Data source '{source}' marked DEGRADED "
                    f"(failures: {m.consecutive_failures})"
                )
                
                # V1.2: Auto-alert on failover
                if was_healthy:
                    self._send_failover_alert(source, error)
            
            logger.debug(f"Data source '{source}' failure recorded: {error}")
    
    def _send_failover_alert(self, source: str, error: str = None) -> None:
        """Send Telegram alert when a source fails over (V1.2)"""
        try:
            from app.utils.notifications import send_telegram_text
            import asyncio
            
            message = (
                f"⚠️ *Data Source Failover*\n\n"
                f"Source: `{source}`\n"
                f"Status: DEGRADED\n"
                f"Error: {error or 'Unknown'}\n\n"
                f"Auto-switching to fallback sources."
            )
            
            # Run async in thread context
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(send_telegram_text(message))
                else:
                    loop.run_until_complete(send_telegram_text(message))
            except RuntimeError:
                # No event loop, create one
                asyncio.run(send_telegram_text(message))
                
            logger.info(f"Failover alert sent for '{source}'")
        except Exception as e:
            logger.warning(f"Failed to send failover alert: {e}")
    
    def should_skip_source(self, source: str) -> bool:
        """
        Check if a source should be skipped due to degradation.
        Returns False if source is healthy or has recovered from cooldown.
        """
        with self._lock:
            if source not in self._metrics:
                return False
            
            m = self._metrics[source]
            
            if m.status == DataSourceStatus.HEALTHY:
                return False
            
            if m.status == DataSourceStatus.DOWN:
                return True
            
            # DEGRADED: check if cooldown has passed
            if m.last_failure:
                cooldown_end = m.last_failure + timedelta(seconds=self.recovery_seconds)
                if datetime.now() >= cooldown_end:
                    # Cooldown passed, allow retry
                    logger.info(f"Data source '{source}' cooldown expired, allowing retry")
                    return False
            
            return True
    
    def get_source_status(self, source: str) -> DataSourceStatus:
        """Get current status of a source"""
        with self._lock:
            if source not in self._metrics:
                return DataSourceStatus.HEALTHY
            return self._metrics[source].status
    
    def get_degraded_sources(self) -> list:
        """Get list of currently degraded sources"""
        with self._lock:
            return [
                name for name, m in self._metrics.items()
                if m.status in (DataSourceStatus.DEGRADED, DataSourceStatus.DOWN)
            ]
    
    def get_stats(self) -> dict:
        """Get statistics for all sources"""
        with self._lock:
            return {
                name: m.to_dict() for name, m in self._metrics.items()
            }
    
    def get_full_status(self) -> dict:
        """Get full status report for API endpoint"""
        with self._lock:
            sources = {name: m.to_dict() for name, m in self._metrics.items()}
            degraded = self.get_degraded_sources()
            
            return {
                "overall": "healthy" if not degraded else "degraded",
                "degradedSources": degraded,
                "sources": sources,
                "config": {
                    "failureThreshold": self.failure_threshold,
                    "recoverySeconds": self.recovery_seconds,
                },
            }
    
    def reset_session(self) -> None:
        """Reset session-specific counters (call at start of sync job)"""
        with self._lock:
            self._session_failures = {name: 0 for name in self.SOURCES}
    
    def get_session_summary(self) -> dict:
        """Get failures from current sync session"""
        with self._lock:
            return dict(self._session_failures)
    
    def mark_source_down(self, source: str) -> None:
        """Manually mark a source as DOWN (e.g., known outage)"""
        with self._lock:
            if source in self._metrics:
                self._metrics[source].status = DataSourceStatus.DOWN
                logger.warning(f"Data source '{source}' manually marked DOWN")
    
    def mark_source_healthy(self, source: str) -> None:
        """Manually restore a source to HEALTHY status"""
        with self._lock:
            if source in self._metrics:
                self._metrics[source].status = DataSourceStatus.HEALTHY
                self._metrics[source].consecutive_failures = 0
                logger.info(f"Data source '{source}' manually restored to HEALTHY")


# Global tracker instance
failure_tracker = FailureTracker(
    failure_threshold=getattr(settings, 'data_source_failure_threshold', 2),
    recovery_seconds=getattr(settings, 'data_source_recovery_period', 300),
)
