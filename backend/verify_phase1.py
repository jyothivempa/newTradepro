
import time
import logging
import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.getcwd())

# Suppress extensive logging
logging.basicConfig(level=logging.ERROR)

print('=== TradeEdge Phase 1 Verification ===')

try:
    from app.engine.signal_generator import generate_signals
    from app.data.archive import get_connection
    from app.api.routes import health_check, get_nifty_trend_status
    print('[OK] Imports successful')
except ImportError as e:
    print(f'[FAIL] Import Error: {e}')
    sys.exit(1)

# 1. Test Signal Generation
print('\n[1] Testing Signal Generator...')
start = time.time()
try:
    results = generate_signals(strategy_type='swing', max_signals=5, max_workers=20)
    print(f'  ✓ Generated {len(results)} signals in {time.time() - start:.1f}s')

    if results:
        s = results[0]['signal']
        print(f'  ✓ Sample Valid Signal: {s.symbol} (Score: {s.score})')
        d = s.to_dict()
        if 'metadata' in d:
             print(f'  ✓ Metadata Found: {str(d["metadata"])[:100]}...')
except Exception as e:
    print(f'  [FAIL] Signal Generation Error: {e}')

# 2. Verify Database Persistence
print('\n[2] Verifying Database...')
try:
    conn = get_connection()
    today = time.strftime('%Y-%m-%d')
    total = conn.execute('SELECT COUNT(*) FROM signals WHERE date(timestamp) >= ?', (today,)).fetchone()[0]
    rejected = conn.execute('SELECT COUNT(*) FROM signals WHERE date(timestamp) >= ? AND rejected = 1', (today,)).fetchone()[0]
    accepted = total - rejected

    print(f'  ✓ Total Logged: {total}')
    print(f'  ✓ Accepted: {accepted}')
    print(f'  ✓ Rejected: {rejected}')

    if rejected > 0:
        reason = conn.execute('SELECT rejection_reason FROM signals WHERE rejected=1 LIMIT 1').fetchone()[0]
        print(f'  ✓ Sample Rejection: {reason}')

    # Check Metadata
    meta = conn.execute('SELECT metadata FROM signals WHERE metadata IS NOT NULL LIMIT 1').fetchone()
    if meta:
        print(f'  ✓ Metadata Column Verified: {meta[0][:50]}...')
except Exception as e:
    print(f'  [FAIL] Database Error: {e}')


# 3. Verify Health & Trends
print('\n[3] Verifying Endpoints...')
try:
    health = asyncio.run(health_check())
    print(f'  ✓ Health Status: {health.status}')
    print(f'  ✓ DB Stats in Health: {health.dbStats}')

    trend = asyncio.run(get_nifty_trend_status())
    print(f'  ✓ NIFTY Trend: {trend["trend"]} ({trend["regime"]})')
except Exception as e:
    print(f'  [FAIL] Endpoint Error: {e}')

print('\n=== Verification Complete ===')
