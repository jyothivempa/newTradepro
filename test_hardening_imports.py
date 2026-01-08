import sys
from pathlib import Path
sys.path.append(str(Path.cwd() / "backend"))

try:
    print("Importing PortfolioRisk...")
    from app.engine.portfolio_risk import portfolio_risk
    print(f"Portfolio Risk: {portfolio_risk}")

    print("Importing AuditLogger...")
    from app.core.audit import audit_logger
    print(f"Audit Logger: {audit_logger}")
    
    audit_logger.log_event("TEST_EVENT", {"status": "ok"})
    print("Audit Event Logged")
    
except Exception as e:
    import traceback
    traceback.print_exc()
