# TradeEdge Pro MVP

A full-stack trading signal application for Indian markets (NSE) featuring intraday-bias and swing trade recommendations.

> ⚠️ **For educational purposes only - not investment advice.** All signals are EOD. Intraday-bias uses historical 15m data for simulation.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                           FRONTEND                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │  Dashboard   │  │  SignalCard  │  │  StockChart  │              │
│  │  (Tabs/Search)│  │  (Signals)   │  │  (ApexCharts)│              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
│                         React + Tailwind CSS                        │
└────────────────────────────────┬────────────────────────────────────┘
                                 │ REST API
┌────────────────────────────────▼────────────────────────────────────┐
│                           BACKEND (FastAPI)                         │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                      API ROUTES                               │  │
│  │  /api/swing  │  /api/intraday-bias  │  /api/stocks/{symbol}  │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                │                                    │
│  ┌─────────────────────────────▼────────────────────────────────┐  │
│  │                    SIGNAL GENERATOR                           │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐   │  │
│  │  │   Swing     │  │  Intraday   │  │     Parallel        │   │  │
│  │  │  Strategy   │  │   Bias      │  │  ThreadPoolExecutor │   │  │
│  │  └─────────────┘  └─────────────┘  └─────────────────────┘   │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                │                                    │
│  ┌─────────────────────────────▼────────────────────────────────┐  │
│  │  SCORER (Weighted)          │  RISK MANAGER (Hard Kills)     │  │
│  │  • Trend Strength: 25%      │  • RR < 2.0 → REJECT           │  │
│  │  • Breakout: 20%            │  • SL > 5% → REJECT            │  │
│  │  • Volume: 20%              │  • Trades ≥ 5 → REJECT         │  │
│  │  • RSI/Momentum: 15%        │                                 │  │
│  │  • Market Align: 10%        │  Position Size =                │  │
│  │  Threshold: ≥70/100         │  (Capital × Risk%) / SL Dist   │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                │                                    │
│  ┌─────────────────────────────▼────────────────────────────────┐  │
│  │                      DATA LAYER                               │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐   │  │
│  │  │   Yahoo     │  │   Alpha     │  │  Cache (Redis/CSV)  │   │  │
│  │  │  Finance    │→ │  Vantage    │  │  Daily: 24h TTL     │   │  │
│  │  │  (Primary)  │  │ (Fallback)  │  │  Intraday: 15m TTL  │   │  │
│  │  └─────────────┘  └─────────────┘  └─────────────────────┘   │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🧠 Core Logic

### Swing Strategy (`swing.py`)
```
IF  20EMA > 50EMA (Bullish Trend)
AND ADX > 25 (Strong Trend)
AND RSI in 45-65 (Goldilocks Zone)
AND MACD Histogram > 0 (Positive Momentum)
AND Price > 20-day High (Breakout)
AND Volume > 1.5x Average (Confirmation)
THEN → BUY Signal

Stop Loss = 2×ATR below entry OR below 50EMA
Targets = 1:2 and 1:3 Risk-Reward
```

### Intraday Bias Strategy (`intraday_bias.py`)
```
IF  9EMA crosses above 21EMA (Crossover)
AND Price > VWAP (Bullish Bias)
AND ATR < 2% (Low Volatility)
AND Volume > 1.2x 20-bar Avg (Confirmation)
THEN → BUY Bias

Stop Loss = 1.5×ATR
Targets = 2×ATR, 3×ATR
```

### Data Validation Gate
```python
def validate_df(df):
    if len(df) < 60: return False           # Minimum bars
    if df[OHLCV].isna().any(): return False  # No NaN values
    if not df.index.is_monotonic: return False
    return True
```

### Risk Manager Hard Kills
```python
if risk_reward < 2.0:    reject()  # Poor R:R
if stop_loss_pct > 5.0:  reject()  # SL too wide
if open_trades >= 5:     reject()  # Max exposure
```

---

## 📁 Project Structure

```
TradeEdgePro/
├── backend/
│   ├── app/
│   │   ├── api/routes.py        # REST endpoints
│   │   ├── config.py            # Settings (NIFTY100/200/500)
│   │   ├── data/
│   │   │   ├── fetch_data.py    # Yahoo + Alpha Vantage
│   │   │   ├── cache_manager.py # Redis/CSV hybrid
│   │   │   └── nifty100.json    # Stock universe
│   │   ├── engine/
│   │   │   ├── signal_generator.py
│   │   │   ├── scorer.py        # Weighted scoring
│   │   │   └── risk_manager.py  # Position sizing
│   │   ├── strategies/
│   │   │   ├── base.py          # Abstract + indicators
│   │   │   ├── swing.py         # Daily strategy
│   │   │   └── intraday_bias.py # 15m EOD simulation
│   │   └── main.py              # FastAPI app
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Dashboard.jsx    # Tabs, search, filters
│   │   │   ├── SignalCard.jsx   # Signal display
│   │   │   ├── StockChart.jsx   # ApexCharts
│   │   │   └── RiskCalculator.jsx
│   │   ├── hooks/useSignals.js  # API polling
│   │   └── api/client.js        # Axios client
│   └── package.json
└── docker-compose.yml
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

Open: **Backend** http://localhost:8000/docs | **Frontend** http://localhost:5173

---

## 📊 API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/swing` | Swing signals (daily) |
| `GET /api/intraday-bias` | 15m EOD simulation |
| `GET /api/stocks/{symbol}` | OHLCV data for charts |
| `GET /api/health` | Health + cache stats |
| `POST /api/calculate-position` | Position sizing |

---

## ⚙️ Configuration

```env
STOCK_UNIVERSE=NIFTY100   # NIFTY100, NIFTY200, NIFTY500
MIN_SIGNAL_SCORE=70       # Minimum score threshold
MIN_RISK_REWARD=2.0       # RR gate
MAX_STOP_LOSS_PCT=5.0     # SL gate
MAX_OPEN_TRADES=5         # Portfolio limit
```

---

## 📜 License

MIT - Educational use only
