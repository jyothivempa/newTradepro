"""
TradeEdge Pro - Price Aggregator
Background service that fetches prices and broadcasts to WebSocket subscribers.

Features:
1. Efficient batch fetching (only subscribed symbols)
2. Configurable update interval
3. Error resilience
4. Position P&L calculation
"""
import asyncio
from typing import Dict, Optional
from datetime import datetime

from app.utils.logger import get_logger
from app.data.live_quotes import get_bulk_quotes, get_live_price
from app.realtime.websocket_manager import (
    sio,
    get_all_subscribed_symbols,
    client_state,
)

logger = get_logger(__name__)


class PriceAggregator:
    """
    Background service that fetches prices and broadcasts to all subscribers.
    
    - Runs in asyncio loop
    - Only fetches symbols with active subscribers
    - Configurable broadcast interval (default: 5 seconds)
    """
    
    def __init__(self, interval: float = 5.0):
        self.interval = interval
        self.running = False
        self._task: Optional[asyncio.Task] = None
        self._last_prices: Dict[str, dict] = {}
        self._error_count = 0
        self._max_errors = 10
    
    async def broadcast_prices(self):
        """Main loop: fetch and broadcast prices"""
        logger.info(f"🚀 Price aggregator started (interval: {self.interval}s)")
        
        while self.running:
            try:
                symbols = get_all_subscribed_symbols()
                
                if symbols:
                    # Fetch prices for all subscribed symbols
                    quotes = get_bulk_quotes(symbols)
                    
                    if quotes:
                        self._last_prices.update(quotes)
                        self._error_count = 0
                        
                        # Broadcast to all clients in 'prices' room
                        await sio.emit('price_update', {
                            "prices": quotes,
                            "timestamp": datetime.now().isoformat(),
                            "count": len(quotes),
                        }, room='prices')
                        
                        logger.debug(f"📡 Broadcast {len(quotes)} prices to {len(client_state)} clients")
                
            except Exception as e:
                self._error_count += 1
                logger.error(f"Price broadcast error ({self._error_count}/{self._max_errors}): {e}")
                
                if self._error_count >= self._max_errors:
                    logger.error("Max errors reached, stopping price aggregator")
                    self.running = False
                    break
            
            await asyncio.sleep(self.interval)
        
        logger.info("🛑 Price aggregator stopped")
    
    def start(self):
        """Start the price aggregator background task"""
        if not self.running:
            self.running = True
            self._error_count = 0
            self._task = asyncio.create_task(self.broadcast_prices())
            logger.info("Price aggregator task created")
    
    def stop(self):
        """Stop the price aggregator"""
        self.running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("Price aggregator stopped")
    
    def get_last_price(self, symbol: str) -> Optional[dict]:
        """Get last known price for a symbol"""
        return self._last_prices.get(symbol)
    
    def get_status(self) -> dict:
        """Get aggregator status"""
        return {
            "running": self.running,
            "interval": self.interval,
            "cached_symbols": len(self._last_prices),
            "error_count": self._error_count,
        }


# Global instance
price_aggregator = PriceAggregator(interval=5.0)


async def start_price_aggregator():
    """Start price aggregator (call from FastAPI lifespan)"""
    price_aggregator.start()


async def stop_price_aggregator():
    """Stop price aggregator"""
    price_aggregator.stop()
