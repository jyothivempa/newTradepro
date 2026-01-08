"""
TradeEdge Pro - Notifications & Interactive Bot
Handles alerts and interactive Telegram commands.
"""
import os
import asyncio
from typing import Optional
import httpx
from datetime import datetime

# Python-Telegram-Bot (PTB) imports
try:
    from telegram import Update, Bot
    from telegram.constants import ParseMode
    from telegram.ext import Application, CommandHandler, ContextTypes
    PTB_AVAILABLE = True
except ImportError:
    PTB_AVAILABLE = False

from app.strategies.base import Signal
from app.utils.logger import get_logger
from app.config import get_settings
# Actually get_cached_regime is in signal_generator.py usually? 
# No, get_cached_regime is in signal_generator, but definition is in market_regime?
# check market_regime.py: `get_regime_for_nifty`. `get_cached_regime` is in `signal_generator`.
# I should import `get_regime_for_nifty` from `market_regime` to avoid circular import with `signal_generator`.


logger = get_logger(__name__)
settings = get_settings()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
ALERT_SCORE_THRESHOLD = 85

class TelegramBotService:
    """
    Interactive Bot Service using python-telegram-bot
    """
    def __init__(self):
        self.app = None
        self.running = False
        
    async def start(self):
        """Start the bot in background"""
        if not PTB_AVAILABLE or not TELEGRAM_BOT_TOKEN:
            logger.warning("Telegram Bot not started (Dependencies or Token missing)")
            return

        try:
            self.app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
            
            # Add Handlers
            self.app.add_handler(CommandHandler("start", self.cmd_start))
            self.app.add_handler(CommandHandler("status", self.cmd_status))
            # self.app.add_handler(CommandHandler("signals", self.cmd_signals)) # Need DB access
            
            await self.app.initialize()
            await self.app.start()
            
            # Use polling? In web app, webhook is better. 
            # But for simplicity in Phase 3, we use polling in asyncio loop?
            # Application.run_polling() blocks. 
            # We want `updater.start_polling()` equivalent.
            # In PTB v20: `await application.updater.start_polling()`
            
            await self.app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
            self.running = True
            logger.info("🤖 Telegram Bot Started (Polling)")
            
        except Exception as e:
            logger.error(f"Failed to start Telegram Bot: {e}")

    async def stop(self):
        """Stop the bot"""
        if self.app and self.running:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
            self.running = False
            logger.info("🤖 Telegram Bot Stopped")

    # --- Commands ---
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "👋 Welcome to TradeEdge Pro Bot!\n\n"
            "Commands:\n"
            "/status - System Health & Regime\n"
            "/signals - Latest Signals (Coming Soon)"
        )

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            from app.engine.market_regime import get_regime_for_nifty
            regime = get_regime_for_nifty()
            msg = (
                f"✅ **System Online**\n"
                f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                f"📊 **NIFTY Regime**\n"
                f"State: `{regime.regime.value}`\n"
                f"ADX: `{regime.adx:.1f}`\n"
                f"Change: `{regime.change_pct:.2f}%`\n"
            )
            await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            await update.message.reply_text(f"Error fetching status: {e}")


# Global Bot Instance
bot_service = TelegramBotService()


# --- Legacy / Helper implementations ---

def format_signal_message(signal: Signal, strategy: str = "swing") -> str:
    """Format signal for Telegram message"""
    emoji = "🟢" if signal.signal_type == "BUY" else "🔴"
    return f"""
{emoji} *{signal.symbol}* - {signal.signal_type}
━━━━━━━━━━━━━━━
📊 *Strategy:* {strategy.upper()}
🎯 *Score:* {signal.score}/100
📈 *Trend:* {signal.trend_strength}

💰 *Entry:* ₹{signal.entry_low:.0f} - ₹{signal.entry_high:.0f}
🛑 *Stop Loss:* ₹{signal.stop_loss:.0f}
🎯 *Targets:* ₹{signal.targets[0]:.0f} / ₹{signal.targets[1] if len(signal.targets)>1 else 0:.0f}

⚠️ _Educational purposes only_
"""

async def send_telegram_alert_async(signal: Signal, strategy: str = "swing") -> bool:
    """Send alert via HTTP (simpler than using Bot instance for one-off)"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
        
    if signal.score < ALERT_SCORE_THRESHOLD:
        return False
        
    message = format_signal_message(signal, strategy)
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    try:
        async with httpx.AsyncClient() as client:
            await client.post(url, json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "Markdown",
            })
        return True
    except Exception as e:
        logger.error(f"Alert failed: {e}")
        return False

def send_telegram_alert(signal: Signal, strategy: str = "swing") -> bool:
    """Sync wrapper"""
    try:
        return asyncio.run(send_telegram_alert_async(signal, strategy))
    except RuntimeError:
        # Loop already running
        # This happens if called from within FastAPI
        # We should use create_task or await if possible.
        # But for sync caller compatibility:
        # If we are in loop, we can't usage asyncio.run.
        # Ideally signal_generator should be async.
        # For now, fire and forget via threading if needed, or just log error.
        logger.warning("Cannot run async alert from sync context with running loop")
        return False

def is_telegram_configured() -> bool:
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


async def send_telegram_text(message: str) -> bool:
    """Send a plain text message to Telegram (for alerts)"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.debug("Telegram not configured, skipping alert")
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "Markdown",
            })
            if response.status_code == 200:
                logger.info("Telegram alert sent successfully")
                return True
            else:
                logger.warning(f"Telegram API returned {response.status_code}")
                return False
    except Exception as e:
        logger.error(f"Failed to send Telegram text: {e}")
        return False
