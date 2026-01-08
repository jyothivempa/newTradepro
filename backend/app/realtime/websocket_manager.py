"""
TradeEdge Pro - WebSocket Manager
Socket.IO server for real-time price feeds and position updates.

Features:
1. Price subscription rooms
2. Automatic client tracking
3. Position P&L broadcasting
4. Reconnection-friendly state management
"""
import socketio
from typing import Dict, Set, List
from datetime import datetime

from app.utils.logger import get_logger

logger = get_logger(__name__)

# Create Socket.IO server with ASGI support
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*',
    ping_timeout=60,
    ping_interval=25,
    logger=False,  # Reduce noise
    engineio_logger=False,
)

# Client subscriptions: {sid: {"symbols": [], "connected_at": datetime}}
client_state: Dict[str, dict] = {}

# Active subscriptions aggregated: {symbol: set(sids)}
symbol_subscribers: Dict[str, Set[str]] = {}


@sio.event
async def connect(sid, environ):
    """Handle new client connection"""
    client_state[sid] = {
        "symbols": [],
        "connected_at": datetime.now().isoformat(),
        "last_heartbeat": datetime.now().isoformat(),
    }
    logger.info(f"✅ Client connected: {sid}")
    
    # Send welcome message with server info
    await sio.emit('welcome', {
        "message": "Connected to TradeEdge Pro",
        "sid": sid,
        "timestamp": datetime.now().isoformat(),
    }, to=sid)


@sio.event
async def subscribe_prices(sid, data):
    """
    Subscribe to live price updates for symbols.
    
    Args:
        data: {"symbols": ["RELIANCE", "TCS", "INFY"]}
    """
    symbols = data.get("symbols", []) if isinstance(data, dict) else data
    
    if not symbols:
        await sio.emit('error', {"message": "No symbols provided"}, to=sid)
        return
    
    # Limit to 50 symbols per client
    symbols = symbols[:50]
    
    # Update client state
    old_symbols = client_state.get(sid, {}).get("symbols", [])
    client_state[sid]["symbols"] = symbols
    
    # Update symbol_subscribers
    # Remove from old subscriptions
    for sym in old_symbols:
        if sym in symbol_subscribers:
            symbol_subscribers[sym].discard(sid)
            if not symbol_subscribers[sym]:
                del symbol_subscribers[sym]
    
    # Add to new subscriptions
    for sym in symbols:
        if sym not in symbol_subscribers:
            symbol_subscribers[sym] = set()
        symbol_subscribers[sym].add(sid)
    
    # Join prices room
    await sio.enter_room(sid, 'prices')
    
    logger.info(f"📊 Client {sid} subscribed to: {symbols}")
    
    await sio.emit('subscribed', {
        "symbols": symbols,
        "count": len(symbols),
    }, to=sid)


@sio.event
async def unsubscribe_prices(sid, data):
    """Unsubscribe from price updates"""
    symbols = data.get("symbols", []) if isinstance(data, dict) else data
    
    current_symbols = client_state.get(sid, {}).get("symbols", [])
    new_symbols = [s for s in current_symbols if s not in symbols]
    
    client_state[sid]["symbols"] = new_symbols
    
    # Update symbol_subscribers
    for sym in symbols:
        if sym in symbol_subscribers:
            symbol_subscribers[sym].discard(sid)
    
    logger.info(f"📉 Client {sid} unsubscribed from: {symbols}")


@sio.event
async def heartbeat(sid, data):
    """Handle client heartbeat for connection health"""
    if sid in client_state:
        client_state[sid]["last_heartbeat"] = datetime.now().isoformat()
    
    await sio.emit('heartbeat_ack', {
        "timestamp": datetime.now().isoformat()
    }, to=sid)


@sio.event
async def disconnect(sid):
    """Handle client disconnect"""
    # Clean up subscriptions
    old_symbols = client_state.get(sid, {}).get("symbols", [])
    for sym in old_symbols:
        if sym in symbol_subscribers:
            symbol_subscribers[sym].discard(sid)
            if not symbol_subscribers[sym]:
                del symbol_subscribers[sym]
    
    # Remove client state
    client_state.pop(sid, None)
    
    logger.info(f"❌ Client disconnected: {sid}")


def get_all_subscribed_symbols() -> List[str]:
    """Get unique list of all subscribed symbols across all clients"""
    return list(symbol_subscribers.keys())


def get_subscribers_for_symbol(symbol: str) -> Set[str]:
    """Get all client SIDs subscribed to a symbol"""
    return symbol_subscribers.get(symbol, set())


def get_connection_stats() -> dict:
    """Get WebSocket connection statistics"""
    return {
        "connected_clients": len(client_state),
        "total_subscriptions": sum(len(s) for s in client_state.values() if "symbols" in s),
        "unique_symbols": len(symbol_subscribers),
        "symbols": list(symbol_subscribers.keys())[:20],  # Top 20
    }


# Create ASGI app wrapper (to be mounted in main.py)
def create_socket_app(fastapi_app):
    """Create Socket.IO ASGI app wrapping FastAPI"""
    return socketio.ASGIApp(sio, fastapi_app)
