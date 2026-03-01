"""Vigil — Event bus for real-time WebSocket broadcasting.

Publishes investigation progress events to connected WebSocket clients
so the dashboard can show the agent's work in real-time.
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Set

from fastapi import WebSocket

logger = logging.getLogger("vigil.events")

# ─── Connected WebSocket clients ───
_clients: Set[WebSocket] = set()


def register(ws: WebSocket):
    """Register a WebSocket client to receive events."""
    _clients.add(ws)
    logger.info(f"📡 WebSocket client connected ({len(_clients)} total)")


def unregister(ws: WebSocket):
    """Unregister a WebSocket client."""
    _clients.discard(ws)
    logger.info(f"📡 WebSocket client disconnected ({len(_clients)} total)")


async def emit(incident_id: str, event_type: str, data: dict = None):
    """
    Broadcast an event to all connected WebSocket clients.

    Event types:
      - incident_created: New incident received
      - status_changed: Incident status updated
      - tool_called: Agent is calling a tool
      - tool_result: Tool returned a result
      - findings_ready: Investigation complete
      - briefing_ready: Briefing text generated
    """
    event = {
        "incident_id": incident_id,
        "type": event_type,
        "data": data or {},
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    dead = set()
    message = json.dumps(event)

    for ws in _clients:
        try:
            await ws.send_text(message)
        except Exception:
            dead.add(ws)

    for ws in dead:
        _clients.discard(ws)
