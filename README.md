# TradeEdge Pro

**Version**: 2.6.1  
Professional algorithmic trading system for Indian markets (NSE) with institutional-grade risk management.

> ⚠️ **For educational purposes only - not investment advice.** All signals are EOD.

---

## ✨ Features

| Module | Description | Status |
|--------|-------------|--------|
| **Swing Trading** | Daily breakout/pullback signals with multi-timeframe analysis | ✅ Production |
| **Intraday Bias** | Directional bias (Bullish/Bearish/Neutral) for next session | ✅ Production |
| **Market Regime 2.0** | Probabilistic classification (TRENDING/RANGING/VOLATILE/DEAD) | ✅ Production |
| **Risk Intelligence** | Gap stress, drawdown scaling, **capital concentration** | ✅ Production |
| **Validation** | Walk-forward analysis with auto-warnings | ✅ Production |
| **Expectancy Tracker** | Adaptive win rates with **confidence weighting** | ✅ Production |
| **Transparency** | "Why No Trade?" activity log with rejection reasons | ✅ Production |
| **Real-Time Data** | WebSocket price feeds with auto-reconnection | ✅ Production |
| **Monitoring** | Prometheus metrics (`/metrics` endpoint) | 🔄 Skeleton |
| **Async I/O** | Concurrent data fetching for NIFTY 500+ | 🔄 Skeleton |

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         TRADEEDGE PRO V2.5                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌───────────┐  │
│  │   FRONTEND   │◄──►│   WebSocket  │◄──►│   FastAPI    │◄──►│  SQLite   │  │
│  │    React     │    │   Socket.IO  │    │   Backend    │    │  Redis    │  │
│  └──────────────┘    └──────────────┘    └──────────────┘    └───────────┘  │
│                                                │                             │
│                                                ▼                             │
│                                         ┌─────────────┐                      │
│                                         │ Prometheus  │ (V2.5)               │
│                                         │  /metrics   │                      │
│                                         └─────────────┘                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                           DATA PIPELINE                                      │
│                                                                              │
│  Yahoo Finance ──► NSE API ──► Alpha Vantage (Fallback Chain)               │
│                           │                                                  │
│                           ▼                                                  │
│                    ┌─────────────┐                                          │
│                    │   Cache     │  (Adaptive TTL by Regime)                │
│                    │ Redis + CSV │                                          │
│                    └─────────────┘                                          │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                        SIGNAL GENERATION CORE                                │
│                                                                              │
│  ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐       │
│  │  DATA   │──►│STRATEGY │──►│ SCORER  │──►│EXPECTANCY──►│  RISK   │──►OUT │
│  │ Fetch   │   │ Analyze │   │ 0-100   │   │ Filter  │   │ Validate│       │
│  └─────────┘   └─────────┘   └─────────┘   └─────────┘   └─────────┘       │
│                                              Adaptive       Gap Stress       │
│                                              Win Rates      Drawdown SC      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🧠 Core Logic Modules

### 1. Signal Generation Engine (`signal_generator.py`)

```python
# V2.5: CPU-aware parallel scanning
for stock in stock_universe:
    1. Fetch OHLCV data (with failover)
    2. Run strategy analysis
    3. Calculate Adaptive Expectancy (regime-aware rolling win rates)
    4. Score signal (0-100) - RANKING ONLY, not a gate
    5. Apply Regime Filter & Volatility Stops
    6. Validate with Risk Manager (Gap stress, Drawdown, Correlation)
    7. Archive result (Accepted/Rejected) to DB
```

**Key Parameters:**
- `MIN_EXPECTANCY`: > 0.0 (Adaptive from trade history)
- `MAX_STOP_LOSS_PCT`: Dynamic (up to 10% in Volatile)
- `WORKER_POOL`: Auto-calculated (CPUs × 2, max 32)

---

### 2. Market Regime 2.0 (`regime_engine.py`) 🧠

**Probabilistic Multi-Factor Classification:**
- **ADX**: Trend strength
- **Choppiness Index**: Trend efficiency
- **Hurst Exponent**: Persistence vs Mean Reversion
- **ATR Percentile**: Volatility rank

**Regime-Aware Risk Controls:**
| Regime | ATR Stop (k) | Daily Loss Limit | Position Size | Gap Tolerance |
|--------|--------------|------------------|---------------|---------------|
| **TRENDING** | 2.0x | -3.0 R | 100% | 5.0% |
| **RANGING** | 1.5x | -1.5 R | 60% | 3.0% |
| **VOLATILE** | 2.5x | -1.0 R | 50% | 2.0% |
| **DEAD** | - | 0.0 R | 0% | 1.0% |

---

### 3. Production Hardening (V2.3)

#### A. Gap Stress Testing (India-Specific) 🇮🇳
Protects against aggressive NSE gap moves.

```python
# Analyzes worst-case gap from 252-day history
worst_gap = max_gap_over_year(symbol)
if worst_gap > regime_tolerance:
    reject("GAP_RISK_EXCEEDED")
```

#### B. Adaptive Expectancy Tracker
Replaces static 40% assumption with rolling estimates.

```python
# Tracks by (Strategy, Regime, Symbol Type)
estimate = get_expectancy_estimate("swing", "VOLATILE", "stock")
win_rate = estimate.win_rate  # e.g., 0.45 from last 50 trades
```

#### C. Walk-Forward Fail-Fast
Auto-warns on unstable strategies.

```python
if stability_score < 0.6 or avg_expectancy < 0:
    log_critical("STRATEGY_UNSTABLE_WARNING")
    recommend("SUSPEND_TRADING")
```

#### D. Drawdown-Adaptive Sizing
Preserves capital during losing streaks.

| Portfolio Drawdown | Position Multiplier |
|-------------------|---------------------|
| < 5% | **1.0x** (Full) |
| 5% - 10% | **0.7x** |
| 10% - 15% | **0.4x** |
| > 15% | **0.2x** (Survival) |

---

### 5. Critical Operational Safeguards (V2.6)

#### A. Expectancy Confidence Weighting
Prevents over-reacting to small sample sizes.

```python
confidence = min(total_trades / 50, 1.0)
weighted_expectancy = raw_expectancy * confidence
```

**Example**:
- 10 trades → confidence=20% → dampens noisy estimates
- 50+ trades → confidence=100% → full trust

#### B. Capital Concentration Kill Switch 🚨
Blocks new trades if top 3 positions exceed 60% of total portfolio risk.

```python
if top3_risk / total_risk > 0.60:
    reject("CAPITAL_CONCENTRATION")
```

**Impact**: Prevents blow-ups from false diversification.

---

### 6. Production Monitoring (V2.6.1)

#### A. Prometheus Alert Rules 🚨
Production-ready alert definitions in `alert_rules.yml`.

**Critical Alerts**:
```yaml
# Zero signals for 2 days
- alert: NoSignalsGenerated
  expr: increase(tradeedge_signals_generated_total[1d]) == 0
  for: 2d
  severity: critical

# Async fetch degraded
- alert: AsyncFetchDegraded
  expr: failure_rate > 0.05
  severity: critical
```

**Setup**: Configure Prometheus + Alertmanager for Telegram notifications.

#### B. Async Backpressure Control
Graceful degradation on API failures.

```python
# Automatic fallback to sync mode at 5% failure rate
if async_failure_rate > 5%:
    logger.critical("ASYNC_DEGRADED")
    return fetch_all_sync()  # Slow but reliable
```

**Principle**: **Correct data late > Fast data wrong**

---

### 4. Code Quality (V2.4)

#### A. Centralized Configuration
All thresholds in `config.yaml` with Pydantic validation.

```yaml
risk:
  daily_loss_limit_r: 2.0
  gap_tolerance:
    VOLATILE: 2.0
    TRENDING: 5.0
```

#### B. Type Safety
Comprehensive type hints for IDE support and static analysis.

```python
def generate_signals(
    strategy_type: str = "swing",
    max_signals: int = 10,
) -> List[Dict[str, Any]]:
    ...
```

---

### 7. Performance Infrastructure (V2.5 - Skeleton)

> **Note**: V2.5 features are **skeletons** - infrastructure ready, integration pending.

#### A. Async Data Fetching (`fetch_data_async.py`)
```python
# V2.6.1: With backpressure control
results = await batch_fetch_daily_safe(symbols, max_concurrent=50)
```
**Expected Impact**: 20x speedup (10min → 30s for NIFTY 500)  
**V2.6.1**: Auto-fallback to sync at 5% failure rate ✅

#### B. Prometheus Metrics (`/metrics`)
Production observability with custom registry.

**Available Metrics**:
- `tradeedge_signal_scan_duration_seconds`
- `tradeedge_signals_generated_total`
- `tradeedge_cache_hits_total`

**V2.6.1**: Alert rules defined in `alert_rules.yml` ✅

**Access**: http://localhost:8000/metrics

#### C. Adaptive Caching
Regime-aware TTLs and market-time invalidation.

```python
ttl = get_adaptive_ttl("VOLATILE")  # Returns 1800s (30 min)
```

---

## 📊 API Endpoints

### Core APIs
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/swing` | GET | Swing signals with score breakdown |
| `/api/signals/history` | GET | **Activity Log** (Accepted + Rejected) |
| `/api/backtest/walkforward/{symbol}` | GET | Walk-Forward validation |
| `/api/nifty-regime-v2` | GET | Probabilistic Regime Analysis |

### Monitoring (V2.5)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/metrics` | GET | **Prometheus metrics** (scrape target) |
| `/api/audit/compliance-report` | GET | SEBI Compliance Report |

---

## 🚀 Quick Start

### Backend
```bash
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:socket_app --host 127.0.0.1 --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

**URLs:** 
- API Docs: http://localhost:8000/docs
- Metrics: http://localhost:8000/metrics
- Frontend: http://localhost:5173

---

## ⚙️ Configuration

**File**: `backend/config.yaml`

```yaml
risk:
  daily_loss_limit_r: 2.0
  gap_tolerance:
    VOLATILE: 2.0
    RANGING: 3.0
    TRENDING: 5.0

strategy:
  min_risk_reward: 2.0
  max_stop_loss_pct: 5.0
```

**Secrets**: `backend/.env`

```env
STOCK_UNIVERSE=NIFTY100
TELEGRAM_BOT_TOKEN=your_token
REDIS_URL=redis://localhost:6379
```

---

## 🔢 Version History

| Version | Date | Highlights |
|---------|------|------------|
| **V2.6.1** | 2026-01 | **Production monitoring**: Prometheus alerts, Async backpressure |
| **V2.6** | 2026-01 | **Critical gaps**: Confidence weighting, Capital concentration |
| **V2.5-dev** | 2026-01 | **Performance skeleton**: Async I/O, Prometheus, Adaptive Cache |
| **V2.4** | 2026-01 | **Code quality**: YAML config, Type hints |
| **V2.3** | 2026-01 | **Production hardening**: Gap stress, Expectancy tracker, Fail-fast |
| **V2.2** | 2026-01 | **Walk-Forward Engine**, **Drawdown Scaling**, **Activity Log** |
| **V2.1** | 2026-01 | **Expectancy Filter**, **Volatility Stops**, **Regime Kill Switch** |
| **V2.0** | 2026-01 | **Market Regime 2.0**, **Hash-Chain Audit**, **WebSocket** |

---

## 📈 Roadmap

### ✅ Complete
- Production hardening (V2.3)
- Code quality (V2.4)
- Infrastructure skeletons (V2.5)

### 🔄 In Progress
- V2.5 integration (~10-15 hours remaining)

### 🎯 Future
- Machine learning regime classifier
- Options strategies (covered calls)
- Multi-timeframe correlation

---

## 📜 License

MIT - Educational use only

---

## 🙏 Acknowledgments

Built with professional-grade risk management inspired by prop trading desks.
