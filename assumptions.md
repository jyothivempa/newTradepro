# System Assumptions & Failure Modes (V2.0)

## 1. Operational Boundaries
*   **Execution**: This system is **Signal Generation Only**. It does NOT execute trades autonomously. All execution is manual.
*   **Data Latency**: Signals are generated on EOD data. Intraday Bias is based on yesterdays close + pre-market context, NOT real-time ticks.
*   **Market Coverage**: Scaled for NIFTY 500. Not validated for small-cap/penny stocks (< ₹50).

## 2. Risk Management Limitations
*   **Slippage Model**: Uses `max(0.1%, ATR*0.1)`. In extreme gaps (>3SD), real loss may exceed backtest models.
*   **Correlation**: Sector-based correlation assumes sector-movements are the primary correlation driver. Does not account for math-based cointegration.
*   **Kill Switch**: The 'Portfolio Risk Manager' runs *before* signal generation. If the system crashes mid-batch, the kill switch state may not persist correctly without external state hydration (Redis/DB).

## 3. Failure Modes
| Scenario | System Behavior | Mitigation |
|:---|:---|:---|
| **Data Feed Failure** | Auto-switch Yahoo → NSE → Alpha Vantage. If all fail, halts. | Check `/health` endpoint. |
| **Zero Signals** | Returns empty list. | Verify `MarketRegime` is not 'DEAD' or VIX > 35. |
| **Risk Block** | New signals rejected with `RISK_LIMIT` reason. | Review Audit Logs for "RISK_INTERVENTION". |
| **Stale Data** | Checks timestamp of last candle. Rejects if > 24h old. | Manual data refresh required. |

## 4. Compliance & Audit
*   **Logs**: All decisions are immutable (JSONL).
*   **Versioning**: `engine`, `strategy`, and `risk` versions act as the "contract".
*   **State**: Reset daily. History is for audit, not state restoration (unless DB connected).
