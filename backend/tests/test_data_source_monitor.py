"""
TradeEdge Pro - Unit Tests for Data Source Monitor
"""
import pytest
import threading
import time
from datetime import datetime, timedelta

# Add backend to path for imports
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.data.data_source_monitor import (
    FailureTracker,
    DataSourceStatus,
    SourceMetrics,
)


class TestSourceMetrics:
    """Tests for SourceMetrics dataclass"""
    
    def test_initial_metrics(self):
        """Test default values for new metrics"""
        m = SourceMetrics(name="test")
        assert m.consecutive_failures == 0
        assert m.total_successes == 0
        assert m.total_failures == 0
        assert m.status == DataSourceStatus.HEALTHY
    
    def test_success_rate_empty(self):
        """Test success rate with no data returns 100%"""
        m = SourceMetrics(name="test")
        assert m.success_rate == 100.0
    
    def test_success_rate_calculation(self):
        """Test success rate calculation"""
        m = SourceMetrics(name="test", total_successes=7, total_failures=3)
        assert m.success_rate == 70.0
    
    def test_to_dict(self):
        """Test dictionary conversion"""
        m = SourceMetrics(name="yahoo")
        d = m.to_dict()
        assert d["name"] == "yahoo"
        assert d["status"] == "healthy"
        assert "successRate" in d
        assert "consecutiveFailures" in d


class TestFailureTracker:
    """Tests for FailureTracker class"""
    
    @pytest.fixture
    def tracker(self):
        """Fresh tracker for each test"""
        return FailureTracker(failure_threshold=2, recovery_seconds=60)
    
    def test_initial_state(self, tracker):
        """Test tracker starts with healthy sources"""
        assert tracker.get_source_status("yahoo") == DataSourceStatus.HEALTHY
        assert tracker.get_source_status("nse") == DataSourceStatus.HEALTHY
        assert tracker.get_degraded_sources() == []
    
    def test_record_success(self, tracker):
        """Test recording success"""
        tracker.record_success("yahoo")
        stats = tracker.get_stats()
        assert stats["yahoo"]["totalSuccesses"] == 1
        assert stats["yahoo"]["consecutiveFailures"] == 0
    
    def test_record_failure(self, tracker):
        """Test recording failure"""
        tracker.record_failure("yahoo", "Connection timeout")
        stats = tracker.get_stats()
        assert stats["yahoo"]["totalFailures"] == 1
        assert stats["yahoo"]["consecutiveFailures"] == 1
        assert stats["yahoo"]["lastError"] == "Connection timeout"
    
    def test_auto_switch_after_threshold(self, tracker):
        """Test source is marked degraded after threshold failures"""
        # First failure - still healthy
        tracker.record_failure("yahoo", "Error 1")
        assert tracker.get_source_status("yahoo") == DataSourceStatus.HEALTHY
        assert not tracker.should_skip_source("yahoo")
        
        # Second failure - now degraded
        tracker.record_failure("yahoo", "Error 2")
        assert tracker.get_source_status("yahoo") == DataSourceStatus.DEGRADED
        assert tracker.should_skip_source("yahoo")
        assert "yahoo" in tracker.get_degraded_sources()
    
    def test_success_resets_failure_count(self, tracker):
        """Test that success resets consecutive failures"""
        tracker.record_failure("yahoo", "Error")
        assert tracker.get_stats()["yahoo"]["consecutiveFailures"] == 1
        
        tracker.record_success("yahoo")
        assert tracker.get_stats()["yahoo"]["consecutiveFailures"] == 0
        assert tracker.get_source_status("yahoo") == DataSourceStatus.HEALTHY
    
    def test_recovery_after_cooldown(self, tracker):
        """Test that degraded source is retried after cooldown"""
        # Reduce cooldown for testing
        tracker.recovery_seconds = 1
        
        # Trigger degradation
        tracker.record_failure("yahoo", "Error 1")
        tracker.record_failure("yahoo", "Error 2")
        assert tracker.should_skip_source("yahoo") is True
        
        # Wait for cooldown
        time.sleep(1.5)
        
        # Should now allow retry
        assert tracker.should_skip_source("yahoo") is False
    
    def test_session_reset(self, tracker):
        """Test session counters reset"""
        tracker.record_failure("yahoo", "Error")
        summary = tracker.get_session_summary()
        assert summary.get("yahoo", 0) == 1
        
        tracker.reset_session()
        summary = tracker.get_session_summary()
        assert summary.get("yahoo", 0) == 0
    
    def test_manual_mark_down(self, tracker):
        """Test manually marking source as down"""
        tracker.mark_source_down("yahoo")
        assert tracker.get_source_status("yahoo") == DataSourceStatus.DOWN
        assert tracker.should_skip_source("yahoo") is True
    
    def test_manual_restore_healthy(self, tracker):
        """Test manually restoring source to healthy"""
        tracker.record_failure("yahoo", "Error 1")
        tracker.record_failure("yahoo", "Error 2")
        assert tracker.get_source_status("yahoo") == DataSourceStatus.DEGRADED
        
        tracker.mark_source_healthy("yahoo")
        assert tracker.get_source_status("yahoo") == DataSourceStatus.HEALTHY
        assert tracker.should_skip_source("yahoo") is False
    
    def test_get_full_status(self, tracker):
        """Test full status report"""
        status = tracker.get_full_status()
        assert "overall" in status
        assert "sources" in status
        assert "config" in status
        assert status["config"]["failureThreshold"] == 2
    
    def test_thread_safety(self, tracker):
        """Test concurrent access to tracker"""
        errors = []
        
        def record_failures():
            try:
                for _ in range(100):
                    tracker.record_failure("yahoo", "Error")
            except Exception as e:
                errors.append(e)
        
        def record_successes():
            try:
                for _ in range(100):
                    tracker.record_success("nse")
            except Exception as e:
                errors.append(e)
        
        threads = [
            threading.Thread(target=record_failures),
            threading.Thread(target=record_successes),
            threading.Thread(target=record_failures),
            threading.Thread(target=record_successes),
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        # Verify counts are reasonable (may vary due to race conditions in counting)
        stats = tracker.get_stats()
        assert stats["yahoo"]["totalFailures"] == 200
        assert stats["nse"]["totalSuccesses"] == 200


class TestNewSourceRegistration:
    """Tests for handling unknown sources"""
    
    def test_unknown_source_recorded(self):
        """Test that unknown sources are added on first use"""
        tracker = FailureTracker()
        tracker.record_success("new_source")
        
        assert "new_source" in tracker.get_stats()
        assert tracker.get_stats()["new_source"]["totalSuccesses"] == 1
    
    def test_unknown_source_not_skipped(self):
        """Test that unknown sources are not skipped"""
        tracker = FailureTracker()
        assert tracker.should_skip_source("unknown_source") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
