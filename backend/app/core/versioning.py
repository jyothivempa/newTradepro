"""
TradeEdge Pro - Version Registry
Strict versioning for all system components to ensure determinism.
"""

SYSTEM_VERSIONS = {
SYSTEM_VERSIONS = {
    "engine": "2.1.0",           # Expectancy filter added
    "swing_strategy": "2.0.0",   # Volatility-normalized stops
    "bias_engine": "1.0.0",      
    "risk_rules": "2.1.0",       # Regime-aware kill switch & SL caps
    "scoring_model": "1.1.0",    
    "data_feed": "1.0.0",        
    "audit_trail": "2.0.0",      
    "regime_engine": "2.0.0",    
}
}

def get_system_version_header() -> str:
    """Get version header string for API responses"""
    return "; ".join([f"{k}={v}" for k, v in SYSTEM_VERSIONS.items()])
