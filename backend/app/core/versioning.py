"""
TradeEdge Pro - Version Registry
Strict versioning for all system components to ensure determinism.
"""

SYSTEM_VERSIONS = {
    "engine": "2.0.0",           # Core signal generation engine
    "swing_strategy": "1.1.0",   # Swing strategy logic
    "bias_engine": "1.0.0",      # Intraday Bias Engine
    "risk_rules": "2.0.0",       # Risk management rules (circuit breaker, correlation)
    "scoring_model": "1.1.0",    # Scoring weights and logic
    "data_feed": "1.0.0",        # Data fetching and validation
    "audit_trail": "2.0.0",      # Audit logging with hash-chain
    "regime_engine": "2.0.0",    # Probabilistic market regime
}

def get_system_version_header() -> str:
    """Get version header string for API responses"""
    return "; ".join([f"{k}={v}" for k, v in SYSTEM_VERSIONS.items()])
