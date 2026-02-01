"""FastAPI server for the prediction engine."""

import asyncio
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import structlog
import uvicorn

from .config import settings
from .engine import TradingEngine, create_engine
from .polymarket.trading import TradeAction

logger = structlog.get_logger()

# Global engine instance
engine: Optional[TradingEngine] = None


# Request/Response models
class EngineControlRequest(BaseModel):
    dry_run: bool = True
    interval_minutes: int = 15


class TradeRequest(BaseModel):
    market_id: str
    action: str
    size: float
    price: Optional[float] = None


class WeightsRequest(BaseModel):
    technical: float
    sentiment: float
    market_data: float
    volatility: float


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global engine
    engine = create_engine(dry_run=True)
    logger.info("Engine created")
    yield
    if engine and engine.state.running:
        await engine.stop()
    logger.info("Shutdown complete")


app = FastAPI(
    title="Polymarket Prediction Engine API",
    description="API for the Polymarket Prediction Machine",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/engine/state")
async def get_engine_state():
    """Get current engine state."""
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    return engine.get_state()


@app.post("/engine/start")
async def start_engine(request: EngineControlRequest, background_tasks: BackgroundTasks):
    """Start the trading engine."""
    global engine

    if engine and engine.state.running:
        raise HTTPException(status_code=400, detail="Engine already running")

    engine = create_engine(
        dry_run=request.dry_run,
        trade_interval_minutes=request.interval_minutes,
    )

    background_tasks.add_task(engine.run_forever)

    return {"status": "starting", "dry_run": request.dry_run}


@app.post("/engine/stop")
async def stop_engine():
    """Stop the trading engine."""
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    if not engine.state.running:
        raise HTTPException(status_code=400, detail="Engine not running")

    await engine.stop()
    return {"status": "stopped"}


@app.post("/engine/run-cycle")
async def run_cycle():
    """Run a single trading cycle."""
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    result = await engine.run_single_cycle()
    return result


@app.get("/markets")
async def get_markets():
    """Get available crypto markets."""
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    markets = await engine.market_fetcher.fetch_crypto_markets()
    return [
        {
            "id": m.id,
            "question": m.question,
            "description": m.description,
            "outcomes": m.outcomes,
            "outcome_prices": m.outcome_prices,
            "volume": m.volume,
            "liquidity": m.liquidity,
            "end_date": m.end_date.isoformat() if m.end_date else None,
            "category": m.category,
            "active": m.active,
        }
        for m in markets
    ]


@app.get("/markets/{market_id}")
async def get_market(market_id: str):
    """Get specific market."""
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    market = await engine.client.get_market(market_id)
    return {
        "id": market.id,
        "question": market.question,
        "description": market.description,
        "outcomes": market.outcomes,
        "outcome_prices": market.outcome_prices,
        "volume": market.volume,
        "liquidity": market.liquidity,
        "end_date": market.end_date.isoformat() if market.end_date else None,
        "category": market.category,
        "active": market.active,
    }


@app.get("/predictions")
async def get_predictions():
    """Get latest predictions."""
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    return engine.get_predictions()


@app.get("/predictions/{market_id}")
async def get_prediction(market_id: str):
    """Get prediction for specific market."""
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    predictions = engine.get_predictions()
    for pred in predictions:
        if pred["market_id"] == market_id:
            return pred

    raise HTTPException(status_code=404, detail="Prediction not found")


@app.get("/trades")
async def get_trades():
    """Get trade history."""
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    return engine.get_trades()


@app.post("/trades/execute")
async def execute_trade(request: TradeRequest):
    """Execute a manual trade."""
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    # Map action string to TradeAction
    action_map = {
        "buy_yes": TradeAction.BUY_YES,
        "buy_no": TradeAction.BUY_NO,
        "sell_yes": TradeAction.SELL_YES,
        "sell_no": TradeAction.SELL_NO,
    }

    action = action_map.get(request.action.lower())
    if not action:
        raise HTTPException(status_code=400, detail=f"Invalid action: {request.action}")

    from .polymarket.trading import TradeSignal

    signal = TradeSignal(
        market_id=request.market_id,
        action=action,
        confidence=1.0,
        predicted_probability=0.5,
        current_price=request.price or 0.5,
        expected_edge=0.0,
        size_recommendation=request.size,
        reasoning="Manual trade",
    )

    result = await engine.executor.execute_signal(signal)

    return {
        "success": result.success,
        "order_id": result.order_id,
        "market_id": result.market_id,
        "action": result.action.value,
        "size": result.size,
        "price": result.price,
        "error": result.error,
        "timestamp": result.timestamp.isoformat(),
    }


@app.get("/positions")
async def get_positions():
    """Get current positions."""
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    positions = await engine.client.get_positions()
    return [
        {
            "market_id": p.market_id,
            "outcome": p.outcome,
            "size": p.size,
            "avg_price": p.avg_price,
            "current_price": p.current_price,
            "pnl": p.pnl,
        }
        for p in positions
    ]


@app.post("/positions/{market_id}/close")
async def close_position(market_id: str):
    """Close a specific position."""
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    result = await engine.executor.close_position(market_id)
    return {
        "success": result.success,
        "order_id": result.order_id,
        "market_id": result.market_id,
        "action": result.action.value,
        "size": result.size,
        "price": result.price,
        "error": result.error,
    }


@app.post("/positions/close-all")
async def close_all_positions():
    """Close all positions."""
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    results = await engine.executor.close_all_positions()
    return [
        {
            "success": r.success,
            "order_id": r.order_id,
            "market_id": r.market_id,
            "action": r.action.value,
            "size": r.size,
            "price": r.price,
            "error": r.error,
        }
        for r in results
    ]


@app.get("/stats/daily")
async def get_daily_stats():
    """Get daily trading statistics."""
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    return engine.executor.get_daily_stats()


@app.get("/config/weights")
async def get_weights():
    """Get current signal weights."""
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    return engine.predictor.get_weights()


@app.put("/config/weights")
async def update_weights(request: WeightsRequest):
    """Update signal weights."""
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    weights = {
        "technical": request.technical,
        "sentiment": request.sentiment,
        "market_data": request.market_data,
        "volatility": request.volatility,
    }

    # Validate sum
    total = sum(weights.values())
    if abs(total - 1.0) > 0.001:
        raise HTTPException(status_code=400, detail="Weights must sum to 1.0")

    engine.predictor.set_weights(weights)
    return weights


def run_server(host: str = "0.0.0.0", port: int = 8000):
    """Run the API server."""
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
