#!/usr/bin/env python
"""
TradeEdge Pro - CLI Backtest Tool
Run backtests on historical data for strategy validation.

Usage:
    python run_backtest.py --strategy swing --from 2024-01-01 --to 2024-12-31
    python run_backtest.py --strategy swing --symbol RELIANCE.NS
    python run_backtest.py  (uses defaults)
"""
import argparse
import sys
sys.path.insert(0, '.')

from app.engine.backtest import backtest_portfolio

# Default liquid NIFTY stocks
DEFAULT_STOCKS = [
    'RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK',
    'BHARTIARTL', 'ITC', 'SBIN', 'LT', 'BAJFINANCE'
]


def main():
    parser = argparse.ArgumentParser(
        description="TradeEdge Pro Backtest Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_backtest.py --strategy swing --from 2024-01-01 --to 2024-12-31
  python run_backtest.py --symbol RELIANCE.NS
  python run_backtest.py --strategy intraday
        """
    )
    parser.add_argument("--strategy", default="swing", 
                        choices=["swing", "intraday"],
                        help="Strategy to backtest (default: swing)")
    parser.add_argument("--from", dest="start_date", default=None,
                        help="Start date (YYYY-MM-DD)")
    parser.add_argument("--to", dest="end_date", default=None,
                        help="End date (YYYY-MM-DD)")
    parser.add_argument("--symbol", default=None,
                        help="Single symbol to test (default: top 10 NIFTY)")
    
    args = parser.parse_args()
    
    # Get stocks to test
    if args.symbol:
        stocks = [args.symbol]
    else:
        stocks = DEFAULT_STOCKS
    
    print("=" * 50)
    print("TradeEdge Pro - Portfolio Backtest")
    print(f"Strategy: {args.strategy.title()}")
    print(f"Stocks: {len(stocks)}")
    if args.start_date and args.end_date:
        print(f"Period: {args.start_date} to {args.end_date}")
    else:
        print("Period: Default (1 Year)")
    print("=" * 50)
    print()
    
    # Run backtest
    result = backtest_portfolio(
        args.strategy, 
        stocks,
        start_date=args.start_date,
        end_date=args.end_date
    )
    
    if 'error' in result:
        print(f"Error: {result['error']}")
        return
    
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


if __name__ == "__main__":
    main()
