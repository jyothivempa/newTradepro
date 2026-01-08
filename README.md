# TradeEdge Pro

Professional trading signal system for Indian markets (NSE) with AI-powered swing and intraday strategies.

> ⚠️ **For educational purposes only - not investment advice.** All signals are EOD.

---

## ✨ Features

### Core
- **Swing Trading** - Daily breakout/pullback signals with multi-timeframe analysis
- **Intraday Bias** - 15m EOD simulation with VWAP and EMA crossovers
- **Risk Management** - Position sizing, R:R gating, sector concentration limits
- **Market Regime** - TRENDING/RANGING/VOLATILE/DEAD classification

### V1 Enhancements
| Feature | Description |
|---------|-------------|
| **Data Redundancy** | Yahoo → NSE → Alpha Vantage auto-failover |
| **NIFTY 500 Support** | Adaptive workers (10→40) for larger universes |
| **Regime Gating** | -20 score for swing trades in sideways markets |
| **Sector ATR Caps** | Dynamic volatility caps (METAL 3%, IT 2%) |
| **Percentile Scoring** | Top 8% signals vs static threshold |
| **Signal Explainability** | `passed[]` / `failed[]` arrays |
| **Options Hints** | Covered call suggestions in low-vol regimes |
| **Economic Indicators** | RBI rates, inflation as regime inputs |
| **CLI Backtest** | Date-range backtesting via command line |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (React)                            │
│   Dashboard  │  SignalCard  │  StockChart  │  Portfolio Tracker    │
└────────────────────────────────┬────────────────────────────────────┘
                                 │ REST API
┌────────────────────────────────▼────────────────────────────────────┐
│                         BACKEND (FastAPI)                           │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  SIGNAL GENERATOR  →  SCORER  →  RISK MANAGER  →  RESPONSE   │   │
│  └──────────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  DATA: Yahoo → NSE → AlphaVantage  │  CACHE: Redis/CSV       │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

**Links**: Backend http://localhost:8000/docs | Frontend http://localhost:5173

---

## 📊 API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/swing` | Swing signals (daily) |
| `GET /api/intraday-bias` | 15m EOD signals |
| `GET /api/stocks/{symbol}` | OHLCV data |
| `GET /api/health` | Health + cache stats |
| `GET /api/data-sources/health` | Data source status |
| `GET /api/economic-indicators` | RBI rates, inflation |
| `GET /api/options-hint/{symbol}` | Covered call suggestions |
| `POST /api/calculate-position` | Position sizing |
| `POST /api/trades/add` | Portfolio tracker |

---

## 🧪 CLI Tools

### Backtest
```bash
cd backend
python run_backtest.py --strategy swing --from 2024-01-01 --to 2024-12-31
python run_backtest.py --symbol RELIANCE.NS
```

---

## ⚙️ Configuration

```env
# Stock Universe
STOCK_UNIVERSE=NIFTY100          # NIFTY100, NIFTY200, NIFTY500

# Strategy
MIN_SIGNAL_SCORE=70
MIN_RISK_REWARD=2.0
MAX_STOP_LOSS_PCT=5.0
MAX_OPEN_TRADES=5

# Feature Toggles (Optional)
ENABLE_OPTIONS_HINTS=false
ENABLE_ECONOMIC_INDICATORS=false
ADAPTIVE_WORKERS=true

# Alerts
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
```

---

## 📁 Project Structure

```
TradeEdgePro/
├── backend/
│   ├── app/
│   │   ├── api/routes.py           # REST endpoints
│   │   ├── config.py               # Settings
│   │   ├── data/
│   │   │   ├── fetch_data.py       # Data with NSE fallback
│   │   │   ├── data_source_monitor.py  # Health tracking
│   │   │   ├── sector_benchmarks.py    # ATR/volume caps
│   │   │   └── economic_indicators.py  # RBI data
│   │   ├── engine/
│   │   │   ├── signal_generator.py # Parallel scanning
│   │   │   ├── scorer.py           # Regime-aware scoring
│   │   │   ├── risk_manager.py     # Position sizing
│   │   │   └── market_regime.py    # TRENDING/RANGING
│   │   └── strategies/
│   │       ├── swing.py            # Pullback + breakout
│   │       ├── intraday_bias.py    # Sector ATR caps
│   │       └── options_hints.py    # Covered calls
│   ├── run_backtest.py             # CLI backtest tool
│   └── requirements.txt
├── frontend/
│   ├── src/components/
│   │   ├── Dashboard.jsx
│   │   ├── SignalCard.jsx
│   │   └── Portfolio.jsx
│   └── package.json
└── docker-compose.yml
```

---

## 📜 License

MIT - Educational use only
