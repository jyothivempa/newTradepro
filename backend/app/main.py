"""
TradeEdge Pro - FastAPI Main Application
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import get_settings
from app.utils.logger import get_logger
from app.engine.signal_generator import load_stock_universe
from app.scheduler import start_scheduler, stop_scheduler
from app.utils.notifications import bot_service

logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Startup
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Stock universe: {settings.stock_universe}")
    
    # Validate stock universe
    stocks = load_stock_universe()
    logger.info(f"Loaded {len(stocks)} stocks")
    
    # Start Scheduler
    start_scheduler()
    
    # Start Telegram Bot
    await bot_service.start()
    
    yield
    
    # Shutdown
    stop_scheduler()
    await bot_service.stop()
    logger.info("Shutting down TradeEdge Pro")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="""
    ## TradeEdge Pro API
    
    Trading signal application for Indian markets (NSE).
    
    ### ⚠️ Disclaimer
    **For educational purposes only - not investment advice.**
    
    All signals are EOD (End of Day). Intraday-bias picks use historical 15m data for simulation.
    
    ### Features
    - 📊 Swing trade signals (daily)
    - ⚡ Intraday bias signals (15m EOD simulation)
    - 🎯 Position sizing calculator
    - 📈 Stock OHLCV data for charting
    """,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(router)


@app.get("/")
async def root():
    """Root endpoint with API info"""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/api/health",
        "disclaimer": "For educational purposes only - not investment advice",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
