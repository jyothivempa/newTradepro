"""
Run Portfolio Backtest
Tests swing strategy on top 10 NIFTY stocks
"""
import sys
sys.path.insert(0, '.')

from app.engine.backtest import backtest_portfolio

# Top 10 liquid NIFTY stocks
STOCKS = [
    'RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK',
    'BHARTIARTL', 'ITC', 'SBIN', 'LT', 'BAJFINANCE'
]

print("=" * 50)
print("TradeEdge Pro - Portfolio Backtest")
print("Strategy: Swing | Stocks: 10 | Period: 1 Year")
print("=" * 50)
print()

result = backtest_portfolio('swing', STOCKS)

if 'error' in result:
    print(f"Error: {result['error']}")
else:
    print(f"📊 Stocks Tested:    {result.get('symbolCount', 0)}")
    print(f"📈 Total Trades:     {result.get('totalTrades', 0)}")
    print(f"✅ Win Rate:         {result.get('overallWinRate', 0)}%")
    print(f"💰 Avg Expectancy:   {result.get('avgExpectancy', 0)}% per trade")
    print(f"📉 Avg Max Drawdown: {result.get('avgMaxDrawdown', 0)}%")
    print()
    
    print("=" * 50)
    print("Individual Stock Results")
    print("=" * 50)
    
    for stock in result.get('symbols', []):
        print(f"\n{stock['symbol']}")
        print(f"  Trades: {stock['totalTrades']}")
        print(f"  Win Rate: {stock['winRate']}%")
        print(f"  Expectancy: {stock['expectancy']}%")
        print(f"  Max DD: {stock['maxDrawdownPct']}%")
