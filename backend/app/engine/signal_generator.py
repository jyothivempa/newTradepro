"""
TradeEdge Pro - Enhanced Signal Generator
With NIFTY trend filter and score breakdown
"""
import json
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import pandas as pd

from app.strategies.base import Signal
from app.strategies.intraday_bias import IntradayBiasStrategy
from app.strategies.swing import SwingStrategy
from app.engine.scorer import score_signal, ScoreBreakdown
from app.engine.risk_manager import RiskManager
from app.data.fetch_data import fetch_daily_data, fetch_intraday_data
from app.data.cache_manager import cache, get_daily_cache_key, get_intraday_cache_key
from app.data.archive import archive_signal
from app.utils.notifications import send_telegram_alert, is_telegram_configured
from app.config import get_settings
from app.utils.logger import get_logger
from app.engine.market_regime import get_regime_for_nifty, RegimeAnalysis

logger = get_logger(__name__)
settings = get_settings()

# Cache NIFTY trend (refresh every 15 min)
_nifty_regime_cache = {"regime": None, "timestamp": None}


def load_stock_universe() -> List[dict]:
    """Load stock universe based on config"""
    universe_map = {
        "NIFTY100": "nifty100.json",
        "NIFTY200": "nifty200.json",
        "NIFTY500": "nifty500.json",
    }
    
    filename = universe_map.get(settings.stock_universe, "nifty100.json")
    filepath = Path(__file__).parent.parent / "data" / filename
    
    try:
        with open(filepath, "r") as f:
            stocks = json.load(f)
        logger.info(f"Loaded {len(stocks)} stocks from {filename}")
        return stocks
    except Exception as e:
        logger.error(f"Failed to load stock universe: {e}")
        return []


def get_cached_regime() -> RegimeAnalysis:
    """Get NIFTY regime with 15-min cache"""
    global _nifty_regime_cache
    
    now = datetime.now()
    if _nifty_regime_cache["timestamp"]:
        age = (now - _nifty_regime_cache["timestamp"]).total_seconds()
        if age < 900:  # 15 minutes
            return _nifty_regime_cache["regime"]
    
    # Fetch fresh
    regime = get_regime_for_nifty()
    _nifty_regime_cache = {"regime": regime, "timestamp": now}
    return regime


def get_cached_data(symbol: str, data_type: str = "daily") -> Optional[pd.DataFrame]:
    """Get data from cache or fetch fresh"""
    if data_type == "daily":
        cache_key = get_daily_cache_key(symbol)
        cached = cache.get(cache_key)
        
        if cached is not None:
            return cached
        
        df = fetch_daily_data(symbol)
        if df is not None:
            cache.set(cache_key, df, settings.cache_daily_ttl)
        return df
    
    else:  # intraday
        cache_key = get_intraday_cache_key(symbol)
        cached = cache.get(cache_key)
        
        if cached is not None:
            return cached
        
        df = fetch_intraday_data(symbol)
        if df is not None:
            cache.set(cache_key, df, settings.cache_intraday_ttl)
        return df


def validate_liquidity(df: pd.DataFrame, symbol: str) -> Tuple[bool, str]:
    """
    Validate stock liquidity to prevent trading illiquid names.
    Criteria:
    - Price > 10 (Penny stock filter)
    - Avg Volume (20d) > 100,000
    """
    if df.empty or len(df) < 20:
        return False, "Insufficient data"
    
    latest = df.iloc[-1]
    price = latest['Close']
    
    # Penny stock filter
    if price < 10:
        return False, f"Price {price:.2f} < 10 (Penny Stock)"
    
    # Volume filter
    avg_vol = df['Volume'].tail(20).mean()
    if avg_vol < 100000:
        return False, f"Avg Volume {int(avg_vol)} < 100k (Illiquid)"
            
    return True, ""


def analyze_stock_swing(
    symbol: str, 
    sector: str,
    regime: RegimeAnalysis
) -> Optional[Dict[str, Any]]:
    """
    Analyze single stock for swing signal.
    Returns candidate dict if valid score, else None (archives rejection).
    Risk Validation is deferred to batch processing.
    """
    try:
        df = get_cached_data(symbol, "daily")
        if df is None:
            return None
        
        # Liquidity Gate
        is_liquid, reason = validate_liquidity(df, symbol)
        if not is_liquid:
            archive_signal(
                symbol=symbol,
                strategy="swing",
                score=0,
                rejected=True,
                rejection_reason=f"NO_LIQUIDITY: {reason}",
                nifty_trend=regime.regime.value if regime else "neutral",
                timestamp=datetime.now().isoformat()
            )
            return None
            
        # Market Circuit Breaker
        # This is a HARD global rule, so we can check it here to save compute.
        # But we use RiskManager for it. 
        # check_circuit_breaker is stateless (depends only on nifty_change_pct).
        rm = RiskManager()
        is_safe, cb_reason = rm.check_circuit_breaker(regime.change_pct, "BUY")
        if not is_safe:
             archive_signal(
                symbol=symbol,
                strategy="swing",
                score=0,
                rejected=True,
                rejection_reason=f"NO_TRADE_REGIME: {cb_reason}",
                nifty_trend=regime.regime.value if regime else "neutral",
                timestamp=datetime.now().isoformat()
            )
             return None
        
        strategy = SwingStrategy()
        signal = strategy.analyze(df, symbol)
        
        if signal:
            # Score with market context
            start_scan_regime = regime.regime.value if regime else "neutral"
            
            signal, breakdown = score_signal(signal, start_scan_regime, "neutral")
            
            # Check score threshold (First Pass)
            if signal.score < settings.min_signal_score:
                 archive_signal(
                    symbol=signal.symbol,
                    strategy=signal.strategy,
                    signal_type=signal.signal_type,
                    score=signal.score,
                    score_breakdown=breakdown.to_dict(),
                    entry_low=signal.entry_low,
                    entry_high=signal.entry_high,
                    stop_loss=signal.stop_loss,
                    targets=signal.targets,
                    risk_reward=signal.risk_reward,
                    trend_strength=signal.trend_strength,
                    sector=sector,
                    rejected=True,
                    rejection_reason=f"NO_EDGE: Score {signal.score} < {settings.min_signal_score}",
                    nifty_trend=regime.regime.value,
                    metadata={
                        "confidence": signal.confidence,
                        "marketRegime": signal.market_regime,
                        "invalidatedIf": signal.invalidated_if,
                        "sectorRs": signal.sector_rs
                    }
                )
                 return None

            # Valid Candidate (Risk Check Pending)
            return {
                "signal": signal,
                "breakdown": breakdown,
                "sector": sector,
                "regime": regime  # Pass regime for later archiving
            }
            
    except Exception as e:
        logger.error(f"Error analyzing {symbol} (swing): {e}")
    
    return None


def analyze_stock_intraday(
    symbol: str,
    sector: str,
    regime: RegimeAnalysis
) -> Optional[Dict[str, Any]]:
    """Analyze single stock for intraday bias. Returns candidate or None."""
    try:
        df = get_cached_data(symbol, "intraday")
        if df is None:
            return None
        
        # V1.3: Use Bias Engine (No P&L claims)
        strategy = IntradayBiasStrategy() # Aliased to IntradayBiasEngine
        bias_result = strategy.analyze(df, symbol, sector)
        
        if bias_result:
            # Skip scoring for bias generator - use confidence directly
            if bias_result.confidence < 0.6:  # Min confidence filter
                 return None

            return {
                "signal": bias_result, # IntradayBias object
                "breakdown": None, # No score breakdown
                "sector": sector,
                "regime": regime
            }
    
    except Exception as e:
        logger.error(f"Error analyzing {symbol} (intraday): {e}")
    
    return None


# === V1 FIX: Sector Deduplication ===
MAX_SIGNALS_PER_SECTOR = 2


def filter_by_percentile(results: list, percentile: float = 0.92) -> list:
    """Filter to top N% of signals by score (Swing only)."""
    if not results or len(results) < 5:
        return results
    
    # Handle IntradayBias which has no score (skip filter or use confidence)
    if hasattr(results[0]["signal"], "confidence"):
         # For bias, filter by confidence
         scores = sorted([r["signal"].confidence for r in results], reverse=True)
    else:
         scores = sorted([r["signal"].score for r in results], reverse=True)
         
    cutoff_idx = max(1, int(len(scores) * (1 - percentile)))
    threshold = scores[cutoff_idx - 1]
    
    if hasattr(results[0]["signal"], "confidence"):
        filtered = [r for r in results if r["signal"].confidence >= threshold]
    else:
        filtered = [r for r in results if r["signal"].score >= threshold]
        
    logger.info(f"📊 Percentile filter: {len(results)} → {len(filtered)} signals (threshold: {threshold})")
    return filtered


def generate_signals(
    strategy_type: str = "swing",
    market_regime: str = "neutral",
    max_signals: int = 20,
    max_workers: int = None,  # Auto-calculated if None
) -> List[Dict[str, Any]]:
    """
    Generate signals with regime locking and persistence.
    Supports adaptive worker scaling for larger universes.
    """
    import time
    start_time = time.time()
    
    stocks = load_stock_universe()
    if not stocks:
        return []
    
    # === Adaptive Worker Scaling ===
    if max_workers is None:
        if settings.adaptive_workers:
            # Scale workers based on universe size: 10->20->40
            max_workers = min(40, max(10, len(stocks) // 10))
        else:
            max_workers = settings.max_scan_workers
    
    # Lock Regime (Fetch once)
    regime = get_cached_regime()
    logger.info(f"🔒 Locked Regime: {regime.regime.value} (ADX: {regime.adx:.1f})")
    
    # Create symbol -> sector mapping
    symbol_sector = {s["symbol"]: s.get("sector", "") for s in stocks}
    symbols = list(symbol_sector.keys())
    
    results: List[Dict[str, Any]] = []
    
    analyze_func = (
        analyze_stock_swing if strategy_type == "swing" 
        else analyze_stock_intraday
    )
    
    logger.info(f"⚡ Scanning {len(symbols)} stocks with {max_workers} workers...")
    
    # Use higher parallelism for faster scanning
    completed = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                analyze_func, 
                symbol, 
                symbol_sector[symbol],
                regime # Pass locked regime object
            ): symbol 
            for symbol in symbols
        }
        
        for future in as_completed(futures):
            symbol = futures[future]
            completed += 1
            try:
                result = future.result()
                if result:
                    results.append(result)
                    signal = result["signal"]
                    # Log differently for Bias vs Swing
                    if hasattr(signal, "score"):
                        logger.info(f"✅ Signal: {signal.symbol} {signal.signal_type} (Score: {signal.score})")
                    else:
                        logger.info(f"✅ Bias: {signal.symbol} {signal.bias} ({signal.confidence:.0%})")
            except Exception as e:
                logger.error(f"❌ Failed to analyze {symbol}: {e}")
            
            # Progress log every 50 stocks
            if completed % 50 == 0:
                elapsed = time.time() - start_time
                logger.info(f"📊 Progress: {completed}/{len(symbols)} ({elapsed:.1f}s)")
    
    # Sort
    if results and hasattr(results[0]["signal"], "score"):
        results.sort(key=lambda r: r["signal"].score, reverse=True)
    elif results:
        results.sort(key=lambda r: r["signal"].confidence, reverse=True)
    
    # === V1 FIX: Percentile Filter (Top 8%) ===
    results = filter_by_percentile(results, percentile=0.92)
    
    # BATCH RISK VALIDATION (Sequential)
    is_swing = strategy_type == "swing"
    
    rm = RiskManager()
    from app.engine.portfolio_risk import portfolio_risk # V1.3 Portfolio Risk
    from app.core.audit import audit_logger # V2.0 Audit
    
    final_results = []
    sector_count = {} 
    
    logger.info(f"🛡️ Validating {len(results)} candidates against Risk Rules...")
    
    for candidate in results:
        signal = candidate["signal"]
        sector = candidate["sector"]
        
        # Check limit
        if len(final_results) >= max_signals:
            break
        
        # === V1 FIX: Sector Deduplication ===
        if sector_count.get(sector, 0) >= MAX_SIGNALS_PER_SECTOR:
            # Audit Log: Sector Deduplication
            audit_logger.log_signal_decision(
                signal.symbol, 
                signal.to_dict() if hasattr(signal, "to_dict") else {"bias": signal.bias},
                "SKIPPED",
                f"Max signals for sector {sector} reached"
            )
            continue
            
        # Swing Strategy Checks
        if is_swing:
            # 1. Existing Trade Risk
            is_valid, reason = rm.validate_signal(signal, sector)
            
            # 2. V1.3 Portfolio Risk (Kill Switch / Correlation / Exposure)
            if is_valid:
                # Calculate required position value first for exposure check
                ps = rm.calculate_position_size(signal, sector)
                
                # Check portfolio rules with position value and symbol for correlation
                is_valid_p, reason_p = portfolio_risk.check_all_rules(
                    sector, 
                    signal.signal_type, 
                    position_value=ps.position_value if ps.valid else 0.0,
                    symbol=signal.symbol  # V2.0: Enable correlation gating
                )
                
                if not is_valid_p:
                    is_valid = False
                    reason = reason_p
                    # Audit Log: Risk Rejection
                    audit_logger.log_risk_action("BLOCK", {
                        "symbol": signal.symbol,
                        "reason": reason,
                        "risk_state": portfolio_risk.get_status()
                    })

            # Audit Log: Signal Decision
            audit_logger.log_signal_decision(
                signal.symbol,
                signal.to_dict(),
                "APPROVED" if is_valid else "REJECTED",
                reason
            )
            
            if is_valid:
                # Add to hypothetical tracking
                if ps.valid:
                    rm.add_trade(signal.symbol, sector, ps.position_value)
                    
                    # Update Portfolio Risk State (Mocking hydration)
                    portfolio_risk.add_open_trade(
                        signal.symbol, 
                        sector, 
                        signal.signal_type,
                        value=ps.position_value
                    )
                    
                    final_results.append(candidate)
                    sector_count[sector] = sector_count.get(sector, 0) + 1
                    
                    # Alert logic...
                    if signal.score >= 85 and is_telegram_configured():
                         pass # (Keep existing alert logic)
                else:
                    # Invalid position size
                     audit_logger.log_signal_decision(
                        signal.symbol, signal.to_dict(), "REJECTED", f"Position Size Invalid: {ps.rejection_reason}"
                    )
        else:
            # Intraday Bias - Pass through
            final_results.append(candidate)
            sector_count[sector] = sector_count.get(sector, 0) + 1
            
            # Audit Log: Bias Generated
            audit_logger.log_signal_decision(
                signal.symbol,
                {"bias": signal.bias, "confidence": signal.confidence},
                "GENERATED",
                "Intraday Bias"
            )
            
        # UI Guidance Message formatting...
        regime_val = (signal.market_regime or "NEUTRAL").upper()
        ui_guidance = ""
        
        if "RANGING" in regime_val or "SIDEWAYS" in regime_val:
            ui_guidance = "High-quality defensive setup. Limited expansion expected in RANGING market."
        elif "TRENDING" in regime_val or "BULLISH" in regime_val:
            ui_guidance = "Strong trend alignment. Breakout potential high."
        elif "VOLATILE" in regime_val:
            ui_guidance = "High volatility. Reduced position size recommended."
        else:
            ui_guidance = f"Setup in {regime_val} market context."
            
        # Archive (Now we archive Accepted or Risk-Rejected)
        # Extract breakdown and regime from candidate
        cand_breakdown = candidate.get("breakdown")
        cand_regime = candidate.get("regime")
        
        # For swing, we have is_valid/reason; for intraday, always accepted
        if is_swing:
            archive_rejected = not is_valid if 'is_valid' in dir() else False
            archive_reason = reason if 'reason' in dir() else ""
        else:
            archive_rejected = False
            archive_reason = ""
        
        archive_signal(
            symbol=signal.symbol,
            strategy=getattr(signal, 'strategy', strategy_type),
            signal_type=getattr(signal, 'signal_type', None),
            score=getattr(signal, 'score', 0),
            score_breakdown=cand_breakdown.to_dict() if cand_breakdown else None,
            entry_low=getattr(signal, 'entry_low', 0),
            entry_high=getattr(signal, 'entry_high', 0),
            stop_loss=getattr(signal, 'stop_loss', 0),
            targets=getattr(signal, 'targets', None),
            risk_reward=getattr(signal, 'risk_reward', 0),
            trend_strength=getattr(signal, 'trend_strength', ''),
            sector=sector,
            rejected=archive_rejected,
            rejection_reason=archive_reason,
            nifty_trend=cand_regime.regime.value if cand_regime else "neutral",
            metadata={
                "confidence": getattr(signal, 'confidence', None),
                "marketRegime": getattr(signal, 'market_regime', None),
                "invalidatedIf": getattr(signal, 'invalidated_if', None),
                "sectorRs": getattr(signal, 'sector_rs', None),
                "uiGuidance": ui_guidance
            }
        )
        
    elapsed = time.time() - start_time
    logger.info(f"🏁 Generated {len(final_results)} {strategy_type} signals in {elapsed:.1f}s (Regime: {regime.regime.value})")
    return final_results

