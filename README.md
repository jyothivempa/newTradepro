# TradeEdge Pro

Professional trading signal system for Indian markets (NSE) with AI-powered swing and intraday strategies.

> ⚠️ **For educational purposes only - not investment advice.** All signals are EOD.

---

## ✨ Features

| Module | Description |
|--------|-------------|
| **Swing Trading** | Daily breakout/pullback signals with multi-timeframe analysis |
| **Intraday Bias** | Directional bias (Bullish/Bearish/Neutral) for next session |
| **Market Regime** | TRENDING/RANGING/VOLATILE/DEAD with 0-1 confidence |
| **Risk Governors** | Circuit breaker, correlation gating, regime scaling |
| **Audit Trail** | SHA-256 hash-chain logging for compliance |
| **Real-Time Data** | WebSocket price feeds with auto-reconnection |

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            TRADEEDGE PRO V2.0                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌───────────┐  │
│  │   FRONTEND   │◄──►│   WebSocket  │◄──►│   FastAPI    │◄──►│  SQLite   │  │
│  │    React     │    │   Socket.IO  │    │   Backend    │    │  Redis    │  │
│  └──────────────┘    └──────────────┘    └──────────────┘    └───────────┘  │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                           DATA PIPELINE                                      │
│                                                                              │
│  Yahoo Finance ──► NSE API ──► Alpha Vantage (Fallback Chain)               │
│                           │                                                  │
│                           ▼                                                  │
│                    ┌─────────────┐                                          │
│                    │   Cache     │  (Redis + CSV Fallback)                  │
│                    │   60s TTL   │                                          │
│                    └─────────────┘                                          │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                        SIGNAL GENERATION CORE                                │
│                                                                              │
│  ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐       │
│  │  DATA   │──►│STRATEGY │──►│ SCORER  │──►│ REGIME  │──►│  RISK   │──►OUT │
│  │ Fetch   │   │ Analyze │   │ 0-100   │   │ Filter  │   │ Validate│       │
│  └─────────┘   └─────────┘   └─────────┘   └─────────┘   └─────────┘       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🧠 Core Logic Modules

### 1. Signal Generation Engine (`signal_generator.py`)

```python
# Parallel scanning with worker pool
for stock in stock_universe:
    1. Fetch OHLCV data (with failover)
    2. Run strategy analysis (Swing/Intraday)
    3. Score signal (0-100 with breakdown)
    4. Apply regime filter (-20 for sideways)
    5. Validate with Risk Manager
    6. Archive to SQLite + Audit Log
```

**Key Parameters:**
- `MIN_SIGNAL_SCORE`: 70
- `MIN_RISK_REWARD`: 2.0
- `MAX_STOP_LOSS_PCT`: 5%

---

### 2. Market Regime 2.0 (`regime_engine.py`) 🧠

**Probabilistic Multi-Factor Classification:**

```
Metrics Used:
┌──────────────────────────────────────────────────────────────┐
│  ADX            │ Trend strength (14-period)                 │
│  Choppiness     │ <38 Trending, >61 Choppy                   │
│  Hurst Exponent │ >0.5 Trend-persistent, <0.5 Mean-reverting │
│  ATR Percentile │ Volatility rank vs 252-day history         │
└──────────────────────────────────────────────────────────────┘
```

**API Response (GET /api/nifty-regime-v2):**
```json
{
  "probabilities": {
    "TRENDING": 0.62,
    "RANGING": 0.18,
    "VOLATILE": 0.15,
    "DEAD": 0.05
  },
  "dominant": "TRENDING",
  "confidence": 0.62,
  "positionMultiplier": 0.85,
  "scoreAdjustment": 4
}
```

**Weighted Position Sizing:**
```python
size = base_size * regime.get_position_multiplier()
# Multiplier = Σ(probability × regime_weight)
# TRENDING: 1.0, RANGING: 0.6, VOLATILE: 0.5, DEAD: 0.0
```

---

### 3. Scoring System (`scorer.py`)

```
Base Score: 100

Deductions:
  - Weak volume:       -15
  - Poor EMA alignment: -20
  - Low ADX (<20):     -10
  - High volatility:   -10
  - Sideways regime:   -20

Bonuses:
  - Strong trend:      +10
  - Volume spike:      +5
  - Sector momentum:   +5

Final = Base - Deductions + Bonuses
```

---

### 4. Risk Management (`risk_manager.py` + `portfolio_risk.py`)

```
┌─────────────────────────────────────────────────────────────────┐
│                      RISK GOVERNORS V2.0                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐   Position blocked if ANY rule triggers   │
│  │ Daily Kill Switch│   P&L < -2R for the day                   │
│  ├──────────────────┤                                            │
│  │ Weekly Kill      │   P&L < -6R for the week                  │
│  ├──────────────────┤                                            │
│  │ Circuit Breaker  │   3 consecutive losing trades             │
│  ├──────────────────┤                                            │
│  │ Correlation Gate │   New trade corr > 0.8 with open trades   │
│  ├──────────────────┤                                            │
│  │ Sector Cap       │   > 30% capital in single sector          │
│  ├──────────────────┤                                            │
│  │ Concentration    │   > 2 trades same sector + direction      │
│  └──────────────────┘                                            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

### 5. Audit Trail (`audit.py`)

```
SHA-256 Hash-Chain:
  
  Entry N-1                      Entry N
  ┌─────────────────┐           ┌─────────────────┐
  │ timestamp       │           │ timestamp       │
  │ event_type      │           │ event_type      │
  │ data            │           │ data            │
  │ prev_hash ──────┼───────────┼► prev_hash      │
  │ hash ───────────┼───────────┘                 │
  └─────────────────┘           │ hash            │
                                └─────────────────┘

API: GET /api/audit/verify?date=2026-01-08
```

---

### 6. WebSocket Real-Time Feed (`websocket_manager.py`)

```javascript
// Client subscribes
socket.emit('subscribe_prices', { symbols: ['RELIANCE', 'TCS'] });

// Server broadcasts every 5s
socket.on('price_update', (data) => {
  // data.prices = { RELIANCE: { ltp: 2850.50, changePct: 1.2 }, ... }
});
```

---

## 📊 API Endpoints

### Core APIs
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/swing` | GET | Swing signals with score breakdown |
| `/api/intraday-bias` | GET | Directional bias for next session |
| `/api/calculate-position` | POST | Risk-based position sizing |
| `/api/backtest/{symbol}` | GET | Historical strategy backtest |

### Risk & Compliance
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/audit/verify` | GET | Verify hash-chain integrity |
| `/api/audit/compliance-report` | GET | Generate SEBI report |
| `/api/audit/portfolio-risk-status` | GET | Current risk state |
| `/ws/status` | GET | WebSocket connection stats |

### Portfolio
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/trades` | GET/POST | List/add trades |
| `/api/trades/{id}/close` | POST | Close trade with P&L |
| `/api/portfolio/stats` | GET | Portfolio summary |

---

## 🚀 Quick Start

### Backend (with WebSocket)
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
- Frontend: http://localhost:5173

---

## ⚙️ Configuration

```env
# Stock Universe
STOCK_UNIVERSE=NIFTY100          # NIFTY100, NIFTY200, NIFTY500

# Strategy Thresholds
MIN_SIGNAL_SCORE=70
MIN_RISK_REWARD=2.0
MAX_STOP_LOSS_PCT=5.0
MAX_OPEN_TRADES=5

# Risk Limits
DAILY_LOSS_LIMIT_R=2.0           # -2R daily kill switch
WEEKLY_LOSS_LIMIT_R=6.0          # -6R weekly kill switch
CIRCUIT_BREAKER_LOSSES=3         # Consecutive losses to pause

# Telegram Alerts
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
```

---

## 📁 Project Structure

```
TradeEdgePro/
├── backend/
│   ├── app/
│   │   ├── api/routes.py              # REST + WebSocket status
│   │   ├── core/
│   │   │   ├── audit.py               # Hash-chain audit log
│   │   │   └── versioning.py          # System versions
│   │   ├── data/
│   │   │   ├── fetch_data.py          # Multi-source failover
│   │   │   ├── portfolio.py           # Trade tracking
│   │   │   └── live_quotes.py         # Price feeds
│   │   ├── engine/
│   │   │   ├── signal_generator.py    # Core signal logic
│   │   │   ├── scorer.py              # 0-100 scoring
│   │   │   ├── market_regime.py       # ADX-based regime
│   │   │   ├── risk_manager.py        # Position-level risk
│   │   │   ├── portfolio_risk.py      # Portfolio-level risk
│   │   │   └── backtest.py            # Historical testing
│   │   ├── realtime/
│   │   │   ├── websocket_manager.py   # Socket.IO server
│   │   │   └── price_aggregator.py    # Price broadcaster
│   │   ├── strategies/
│   │   │   ├── swing.py               # Swing strategy
│   │   │   └── intraday_bias.py       # Intraday bias
│   │   └── utils/
│   │       ├── precision.py           # Decimal calculations
│   │       └── logger.py              # Structured logging
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Dashboard.jsx          # Main dashboard
│   │   │   └── SignalCard.jsx         # Signal display
│   │   ├── hooks/
│   │   │   └── useWebSocket.js        # Real-time hook
│   │   └── pages/
│   │       └── Portfolio.jsx          # Trade tracker
│   └── package.json
└── docker-compose.yml
```

---

## 🔢 Version History

| Version | Date | Highlights |
|---------|------|------------|
| V2.0 | 2026-01 | Circuit breaker, hash-chain audit, WebSocket |
| V1.2 | 2025-12 | Backtest API, Sharpe ratio, STT simulation |
| V1.1 | 2025-11 | Regime confidence, trade logger |
| V1.0 | 2025-10 | Initial release |

---

## 📜 License

MIT - Educational use only
