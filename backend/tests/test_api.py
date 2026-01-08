"""
TradeEdge Pro - Integration Tests for API
"""
import pytest
from fastapi.testclient import TestClient

# Add backend to path for imports
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.main import app


client = TestClient(app)


class TestHealthEndpoint:
    """Tests for /api/health"""
    
    def test_health_returns_200(self):
        """Test health endpoint returns 200"""
        response = client.get("/api/health")
        assert response.status_code == 200
    
    def test_health_returns_status(self):
        """Test health response contains status"""
        response = client.get("/api/health")
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"
    
    def test_health_returns_stock_count(self):
        """Test health response contains stock count"""
        response = client.get("/api/health")
        data = response.json()
        assert "stockCount" in data
        assert data["stockCount"] > 0
    
    def test_health_returns_nifty_trend(self):
        """Test health response contains nifty trend"""
        response = client.get("/api/health")
        data = response.json()
        assert "niftyTrend" in data
        assert data["niftyTrend"] in ["bullish", "bearish", "neutral"]


class TestSwingEndpoint:
    """Tests for /api/swing"""
    
    def test_swing_returns_200(self):
        """Test swing endpoint returns 200"""
        response = client.get("/api/swing")
        assert response.status_code == 200
    
    def test_swing_returns_list(self):
        """Test swing endpoint returns a list"""
        response = client.get("/api/swing")
        data = response.json()
        assert isinstance(data, list)
    
    def test_swing_with_limit(self):
        """Test swing endpoint respects limit parameter"""
        response = client.get("/api/swing?limit=5")
        data = response.json()
        assert len(data) <= 5
    
    def test_swing_signal_structure(self):
        """Test swing signal has required fields"""
        response = client.get("/api/swing?limit=1")
        data = response.json()
        
        if len(data) > 0:
            signal = data[0]
            required_fields = ["symbol", "signal", "entry", "stopLoss", "targets", "score"]
            for field in required_fields:
                assert field in signal, f"Missing field: {field}"


class TestIntradayBiasEndpoint:
    """Tests for /api/intraday-bias"""
    
    def test_intraday_returns_200(self):
        """Test intraday-bias endpoint returns 200"""
        response = client.get("/api/intraday-bias")
        assert response.status_code == 200
    
    def test_intraday_returns_list(self):
        """Test intraday-bias endpoint returns a list"""
        response = client.get("/api/intraday-bias")
        data = response.json()
        assert isinstance(data, list)


class TestStocksEndpoint:
    """Tests for /api/stocks"""
    
    def test_stocks_returns_200(self):
        """Test stocks endpoint returns 200"""
        response = client.get("/api/stocks")
        assert response.status_code == 200
    
    def test_stocks_returns_list(self):
        """Test stocks endpoint returns a list"""
        response = client.get("/api/stocks")
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
    
    def test_stock_has_required_fields(self):
        """Test stock info has required fields"""
        response = client.get("/api/stocks")
        data = response.json()
        
        if len(data) > 0:
            stock = data[0]
            assert "symbol" in stock
            assert "name" in stock
            assert "sector" in stock
    
    def test_stock_detail_returns_data(self):
        """Test stock detail endpoint returns OHLCV data"""
        # First get a valid symbol
        response = client.get("/api/stocks")
        stocks = response.json()
        
        if len(stocks) > 0:
            symbol = stocks[0]["symbol"]
            response = client.get(f"/api/stocks/{symbol}")
            # May return 503 if data is unavailable
            assert response.status_code in [200, 503]
    
    def test_invalid_stock_returns_404(self):
        """Test invalid symbol returns 404"""
        response = client.get("/api/stocks/INVALIDXYZ")
        assert response.status_code == 404


class TestSectorsEndpoint:
    """Tests for /api/sectors"""
    
    def test_sectors_returns_200(self):
        """Test sectors endpoint returns 200"""
        response = client.get("/api/sectors")
        assert response.status_code == 200
    
    def test_sectors_returns_list(self):
        """Test sectors endpoint returns sectors list"""
        response = client.get("/api/sectors")
        data = response.json()
        assert "sectors" in data
        assert isinstance(data["sectors"], list)


class TestRiskSnapshotEndpoint:
    """Tests for /api/risk-snapshot"""
    
    def test_risk_snapshot_returns_200(self):
        """Test risk snapshot endpoint returns 200"""
        response = client.get("/api/risk-snapshot")
        assert response.status_code == 200
    
    def test_risk_snapshot_structure(self):
        """Test risk snapshot has required fields"""
        response = client.get("/api/risk-snapshot")
        data = response.json()
        
        required_fields = ["capital", "riskPerTrade", "openTrades", "maxTrades", "riskUsedToday"]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"


class TestCalculatePositionEndpoint:
    """Tests for /api/calculate-position"""
    
    def test_calculate_position_returns_200(self):
        """Test calculate position endpoint works"""
        response = client.post("/api/calculate-position", json={
            "capital": 100000,
            "risk_percent": 1.0,
            "entry": 1000,
            "stop_loss": 950,
        })
        assert response.status_code == 200
    
    def test_calculate_position_result(self):
        """Test position calculation is correct"""
        response = client.post("/api/calculate-position", json={
            "capital": 100000,
            "risk_percent": 1.0,
            "entry": 1000,
            "stop_loss": 950,
        })
        data = response.json()
        
        # Risk = 1% of 100000 = 1000
        # SL distance = 50
        # Shares = 1000 / 50 = 20
        assert data["shares"] == 20
        assert data["riskAmount"] == 1000.0
        assert data["valid"] is True
    
    def test_invalid_position_rejected(self):
        """Test that entry == stop_loss is rejected"""
        response = client.post("/api/calculate-position", json={
            "capital": 100000,
            "risk_percent": 1.0,
            "entry": 1000,
            "stop_loss": 1000,  # Same as entry
        })
        data = response.json()
        assert data["valid"] is False


class TestNiftyTrendEndpoint:
    """Tests for /api/nifty-trend"""
    
    def test_nifty_trend_returns_200(self):
        """Test nifty trend endpoint returns 200"""
        response = client.get("/api/nifty-trend")
        assert response.status_code == 200
    
    def test_nifty_trend_structure(self):
        """Test nifty trend response has required fields"""
        response = client.get("/api/nifty-trend")
        data = response.json()
        
        assert "trend" in data
        assert "description" in data
        assert "impact" in data


class TestRootEndpoint:
    """Tests for / root"""
    
    def test_root_returns_200(self):
        """Test root endpoint returns 200"""
        response = client.get("/")
        assert response.status_code == 200
    
    def test_root_has_name(self):
        """Test root response has app name"""
        response = client.get("/")
        data = response.json()
        assert "name" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
