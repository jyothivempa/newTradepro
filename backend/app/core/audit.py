"""
TradeEdge Pro - Audit Logger V2.0
Append-only JSONL logging with hash-chain for regulatory defensibility.

Features:
1. Immutable append-only logs (JSONL format)
2. Hash-chain linking (SHA-256, prev_hash → current_hash)
3. Version tagging for all events
4. Compliance report generation
5. Chain verification tool
"""
import json
import hashlib
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

from app.config import get_settings
from app.core.versioning import SYSTEM_VERSIONS

settings = get_settings()


class AuditLogger:
    """
    Append-only logger with hash-chain for audit trail integrity.
    
    Each entry contains:
    - timestamp: ISO format datetime
    - event_type: Category of event
    - versions: All system component versions
    - data: Event payload
    - prev_hash: Hash of previous entry (genesis = 64 zeros)
    - hash: SHA-256 of current entry + prev_hash
    """
    
    GENESIS_HASH = "0" * 64
    
    def __init__(self):
        self.log_dir = Path("logs/audit")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Ensure we have a root logger for fallback
        self.logger = logging.getLogger("audit")
        self.logger.setLevel(logging.INFO)
        
        # Initialize hash chain from existing file
        self._last_hash = self._get_last_hash()
        
    def _get_log_file(self, for_date: Optional[date] = None) -> Path:
        """Get audit log file path for a specific date"""
        if for_date is None:
            for_date = date.today()
        date_str = for_date.strftime("%Y-%m-%d")
        return self.log_dir / f"audit_{date_str}.jsonl"
    
    def _get_last_hash(self) -> str:
        """Read last entry's hash from today's file"""
        log_file = self._get_log_file()
        if log_file.exists():
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    if lines:
                        last_entry = json.loads(lines[-1].strip())
                        return last_entry.get('hash', self.GENESIS_HASH)
            except Exception:
                pass
        return self.GENESIS_HASH
    
    def _compute_hash(self, entry: dict) -> str:
        """
        Compute SHA-256 hash of entry content + prev_hash.
        This creates an immutable chain where tampering breaks the chain.
        """
        # Create a copy without the hash field for hashing
        hashable = {k: v for k, v in entry.items() if k != 'hash'}
        content = json.dumps(hashable, sort_keys=True)
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def log_event(self, event_type: str, data: Dict[str, Any]):
        """
        Log an immutable event to the audit trail with hash-chain.
        
        Args:
            event_type: Category of event (e.g., "SIGNAL_GENERATED", "RISK_BLOCK")
            data: Structured data payload
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "versions": SYSTEM_VERSIONS,
            "data": data,
            "environment": settings.environment,
            "prev_hash": self._last_hash,
        }
        
        # Compute and add hash
        entry["hash"] = self._compute_hash(entry)
        self._last_hash = entry["hash"]
        
        try:
            # Append-only write
            with open(self._get_log_file(), "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            # Fallback to standard logger if file write fails
            self.logger.error(f"Failed to write audit log: {e}")
            self.logger.info(f"AUDIT_FALLBACK: {json.dumps(entry)}")

    def log_signal_decision(self, symbol: str, signal_data: dict, decision: str, reason: str = ""):
        """Specialized logger for signal generation decisions"""
        self.log_event("SIGNAL_DECISION", {
            "symbol": symbol,
            "decision": decision,   # APPROVED, REJECTED, SKIPPED, GENERATED
            "reason": reason,
            "signal_details": signal_data,
        })

    def log_risk_action(self, action: str, details: dict):
        """Specialized logger for risk interventions"""
        self.log_event("RISK_INTERVENTION", {
            "action": action,   # KILL_SWITCH, CIRCUIT_BREAKER, CORRELATION_BLOCK, SECTOR_LIMIT
            "details": details
        })
    
    def log_trade_entry(self, symbol: str, entry_price: float, quantity: int, position_value: float, signal_id: str = ""):
        """Log a trade entry for compliance"""
        self.log_event("TRADE_ENTRY", {
            "symbol": symbol,
            "entry_price": entry_price,
            "quantity": quantity,
            "position_value": position_value,
            "signal_id": signal_id,
        })
    
    def log_trade_exit(self, symbol: str, exit_price: float, pnl: float, exit_reason: str):
        """Log a trade exit for compliance"""
        self.log_event("TRADE_EXIT", {
            "symbol": symbol,
            "exit_price": exit_price,
            "pnl": pnl,
            "exit_reason": exit_reason,
        })


def verify_audit_chain(log_file: Path) -> Tuple[bool, List[str]]:
    """
    Verify hash chain integrity of an audit log file.
    
    Returns:
        (is_valid, list_of_errors)
    """
    errors = []
    prev_hash = AuditLogger.GENESIS_HASH
    
    if not log_file.exists():
        return False, [f"File not found: {log_file}"]
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f, 1):
                try:
                    entry = json.loads(line.strip())
                    
                    # Check prev_hash links correctly
                    if entry.get('prev_hash') != prev_hash:
                        errors.append(f"Line {i}: prev_hash mismatch (expected {prev_hash[:16]}..., got {entry.get('prev_hash', 'missing')[:16]}...)")
                    
                    # Verify hash computation
                    stored_hash = entry.get('hash')
                    computed_hash = hashlib.sha256(
                        json.dumps({k: v for k, v in entry.items() if k != 'hash'}, sort_keys=True).encode('utf-8')
                    ).hexdigest()
                    
                    if stored_hash != computed_hash:
                        errors.append(f"Line {i}: hash mismatch (stored {stored_hash[:16]}..., computed {computed_hash[:16]}...)")
                    
                    prev_hash = stored_hash
                    
                except json.JSONDecodeError as e:
                    errors.append(f"Line {i}: Invalid JSON - {e}")
                    
    except Exception as e:
        errors.append(f"File read error: {e}")
    
    return len(errors) == 0, errors


def get_compliance_report(start_date: date, end_date: date) -> Dict[str, Any]:
    """
    Generate a compliance report for a date range.
    
    Returns summary statistics and chain verification status.
    """
    logger = AuditLogger()
    
    report = {
        "reportGeneratedAt": datetime.now().isoformat(),
        "startDate": start_date.isoformat(),
        "endDate": end_date.isoformat(),
        "systemVersions": SYSTEM_VERSIONS,
        "days": [],
        "summary": {
            "totalEvents": 0,
            "signalDecisions": 0,
            "riskInterventions": 0,
            "tradeEntries": 0,
            "tradeExits": 0,
            "chainIntegrityStatus": "VERIFIED",
        }
    }
    
    current = start_date
    all_valid = True
    
    while current <= end_date:
        log_file = logger._get_log_file(current)
        
        day_report = {
            "date": current.isoformat(),
            "fileExists": log_file.exists(),
            "eventCount": 0,
            "chainValid": True,
            "errors": [],
        }
        
        if log_file.exists():
            is_valid, errors = verify_audit_chain(log_file)
            day_report["chainValid"] = is_valid
            day_report["errors"] = errors[:5]  # Limit to first 5 errors
            
            if not is_valid:
                all_valid = False
            
            # Count events
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        try:
                            entry = json.loads(line.strip())
                            day_report["eventCount"] += 1
                            report["summary"]["totalEvents"] += 1
                            
                            event_type = entry.get("event_type", "")
                            if event_type == "SIGNAL_DECISION":
                                report["summary"]["signalDecisions"] += 1
                            elif event_type == "RISK_INTERVENTION":
                                report["summary"]["riskInterventions"] += 1
                            elif event_type == "TRADE_ENTRY":
                                report["summary"]["tradeEntries"] += 1
                            elif event_type == "TRADE_EXIT":
                                report["summary"]["tradeExits"] += 1
                        except json.JSONDecodeError:
                            pass
            except Exception:
                pass
        
        report["days"].append(day_report)
        current = date(current.year, current.month, current.day + 1) if current.day < 28 else \
                  date(current.year, current.month + 1, 1) if current.month < 12 else \
                  date(current.year + 1, 1, 1)
        
        # Safety: limit to 365 days
        if len(report["days"]) > 365:
            break
    
    report["summary"]["chainIntegrityStatus"] = "VERIFIED" if all_valid else "COMPROMISED"
    
    return report


# Global instance
audit_logger = AuditLogger()
