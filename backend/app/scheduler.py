"""
TradeEdge Pro - Automated Scheduler
Manages daily cron jobs for data fetching and signal generation.
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import asyncio
from datetime import datetime

from app.utils.logger import get_logger
from app.config import get_settings
from app.engine.signal_generator import generate_signals, load_stock_universe
from app.data.fetch_data import fetch_daily_data

logger = get_logger(__name__)
settings = get_settings()

scheduler = AsyncIOScheduler()

async def job_fetch_data():
    """Daily Data Sync Job (16:00 IST) with failure tracking and alerting"""
    from app.data.data_source_monitor import failure_tracker
    
    logger.info("⏳ Starting Daily Data Sync...")
    
    # Reset session counters for this sync run
    failure_tracker.reset_session()
    
    stocks = load_stock_universe()
    if not stocks:
        logger.warning("No stocks found to sync")
        return
        
    symbols = [s["symbol"] for s in stocks]
    total = len(symbols)
    
    count = 0
    failed_symbols = []
    
    for symbol in symbols:
        try:
            await asyncio.to_thread(fetch_daily_data, symbol, "2y") 
            count += 1
            if count % 20 == 0:
                logger.info(f"Synced {count}/{total} stocks")
        except Exception as e:
            logger.error(f"Failed to sync {symbol}: {e}")
            failed_symbols.append(symbol)
    
    # Post-sync summary
    session_summary = failure_tracker.get_session_summary()
    degraded_sources = failure_tracker.get_degraded_sources()
    
    logger.info(f"✅ Daily Data Sync Complete: {count}/{total} stocks updated")
    
    # Alert if there are issues
    if degraded_sources or failed_symbols:
        await _send_sync_alert(
            count, total, failed_symbols, degraded_sources, session_summary
        )


async def _send_sync_alert(
    success: int, 
    total: int, 
    failed_symbols: list, 
    degraded_sources: list,
    session_summary: dict
):
    """Send Telegram alert about data sync issues"""
    try:
        from app.utils.notifications import send_telegram_text
        
        message = f"📊 **Daily Sync Report**\n"
        message += f"━━━━━━━━━━━━━━━\n"
        message += f"✅ Success: {success}/{total}\n"
        
        if degraded_sources:
            message += f"\n⚠️ **Degraded Sources:**\n"
            for src in degraded_sources:
                message += f"  • {src}\n"
        
        if failed_symbols:
            preview = failed_symbols[:5]
            message += f"\n❌ **Failed Symbols ({len(failed_symbols)}):**\n"
            message += ", ".join(preview)
            if len(failed_symbols) > 5:
                message += f" +{len(failed_symbols) - 5} more"
        
        message += f"\n\n_Source Failures: {session_summary}_"
        
        await send_telegram_text(message)
    except Exception as e:
        logger.error(f"Failed to send sync alert: {e}")

async def job_generate_signals():
    """Daily Signal Scan Job (16:15 IST)"""
    logger.info("⏳ Starting Daily Signal Scan...")
    
    # Run heavy computation in thread pool to avoid blocking main loop
    results = await asyncio.to_thread(
        generate_signals, 
        strategy_type="swing", 
        max_workers=10
    )
    
    logger.info(f"✅ Daily Signal Scan Complete. Found {len(results)} signals.")

def start_scheduler():
    """Start the scheduler"""
    if scheduler.running:
        return

    # TZ = Asia/Kolkata
    # 16:00 IST = 10:30 UTC
    # We should use 'Asia/Kolkata' if tzlocal installed or just explicit offsets.
    # APScheduler supports timezone.
    
    try:
        # Schedule Data Fetch: Everyday at 16:00
        scheduler.add_job(
            job_fetch_data,
            CronTrigger(hour=16, minute=0, timezone="Asia/Kolkata"),
            name="daily_data_sync",
            id="daily_data_sync",
            replace_existing=True
        )
        
        # Schedule Signal Gen: Everyday at 16:15
        scheduler.add_job(
            job_generate_signals,
            CronTrigger(hour=16, minute=15, timezone="Asia/Kolkata"),
            name="daily_signal_scan",
            id="daily_signal_scan",
            replace_existing=True
        )
        
        scheduler.start()
        logger.info("📅 Scheduler Started (Timezone: Asia/Kolkata)")
        
        # Log Next Runs
        for job in scheduler.get_jobs():
           logger.info(f"Job '{job.name}' next run: {job.next_run_time}")
           
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")

def stop_scheduler():
    """Stop the scheduler"""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("📅 Scheduler Stopped")
