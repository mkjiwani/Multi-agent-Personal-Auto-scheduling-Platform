"""WebSocket endpoint for live dashboard updates."""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.orchestrator.monitor import resource_monitor
from src.orchestrator.alarm import alarm_system
from src.orchestrator.agent_supervisor import agent_supervisor
from src.llm.ollama_client import OllamaClient

logger = logging.getLogger(__name__)
router = APIRouter()

# Connected WebSocket clients
_connections: list[WebSocket] = []


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for live system metrics and agent status."""
    await websocket.accept()
    _connections.append(websocket)
    logger.info(f"WebSocket client connected (total: {len(_connections)})")

    # Subscribe to metrics
    metrics_queue = resource_monitor.subscribe()

    try:
        while True:
            try:
                metrics = await asyncio.wait_for(metrics_queue.get(), timeout=5.0)
                payload = {
                    "type": "update",
                    "system": metrics.to_dict(),
                    "alarms": alarm_system.get_status(),
                    "agents": agent_supervisor.get_status(),
                    "llm": OllamaClient.get_semaphore_status(),
                }
                await websocket.send_text(json.dumps(payload))
            except asyncio.TimeoutError:
                # Send heartbeat even without new metrics
                await websocket.send_text(json.dumps({"type": "heartbeat"}))
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.debug(f"WebSocket error: {e}")
    finally:
        resource_monitor.unsubscribe(metrics_queue)
        if websocket in _connections:
            _connections.remove(websocket)
