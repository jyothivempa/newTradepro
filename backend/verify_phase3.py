
import sys
import os
import asyncio
import logging

# Add backend to path
sys.path.append(os.getcwd())
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def verify_scheduler():
    logger.info("[1] Verifying Scheduler...")
    try:
        from app.scheduler import scheduler, start_scheduler, stop_scheduler
        print("  ✓ Scheduler Imported")
        
        # Test start/stop (simulated)
        # Note: scheduler.start() might start loop? APScheduler AsyncIOScheduler needs running loop.
        # We are in async function, so loop is running.
        start_scheduler()
        print(f"  ✓ Scheduler Started (Running: {scheduler.running})")
        stop_scheduler()
        print(f"  ✓ Scheduler Stopped (Running: {scheduler.running})")
        
    except Exception as e:
        print(f"  X Scheduler Failed: {e}")

async def verify_bot():
    logger.info("\n[2] Verifying Telegram Bot...")
    try:
        from app.utils.notifications import TelegramBotService, bot_service
        print("  ✓ Bot Service Imported")
        
        # We can't really start it without TOKEN or valid connection
        # But we can check class structure
        if isinstance(bot_service, TelegramBotService):
            print("  ✓ Bot Instance Created")
        else:
            print("  X Bot Instance Invalid")
            
    except Exception as e:
        print(f"  X Bot Verify Failed: {e}")

def verify_docker_files():
    logger.info("\n[3] Verifying Docker Config...")
    files = [
        "backend/Dockerfile",
        "frontend/Dockerfile",
        "../docker-compose.yml" # Relative to backend cwd? No, absolute check better.
    ]
    
    # We are usually running from backend dir in commands
    # So ../docker-compose.yml is correct
    
    for f in files:
        if os.path.exists(f):
            print(f"  ✓ Found {f}")
        else:
            print(f"  X Missing {f}")

async def main():
    await verify_scheduler()
    await verify_bot()
    verify_docker_files()

if __name__ == "__main__":
    asyncio.run(main())
