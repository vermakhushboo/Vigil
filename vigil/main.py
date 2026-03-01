"""Vigil — FastAPI entrypoint.

Receives Alertmanager webhooks, creates Incident objects,
triggers the AI agent investigation pipeline, and serves the
real-time dashboard via WebSocket.
"""
import os
import uuid
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from vigil.config import settings
from vigil.models.incident import Incident, IncidentStatus, IncidentFindings
from vigil.agents.orchestrator import investigate
from vigil.agents.synthesiser import generate_briefing
from vigil.tools.runbook_search import load_runbooks
from vigil.memory.seed import seed_past_incidents
from vigil import events

# ─── Logging ───
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("vigil")

# ─── In-memory incident store ───
incidents: Dict[str, Incident] = {}

# ─── Deduplication: track active alerts by (alertname, service) ───
_active_alerts: Dict[str, str] = {}


# ─── Lifespan ───
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: seed ChromaDB with runbooks and past incidents."""
    logger.info("🚀 Vigil API starting up...")
    try:
        load_runbooks()
        logger.info("📚 Runbooks loaded into ChromaDB")
    except Exception as e:
        logger.warning(f"⚠️ Failed to load runbooks: {e}")

    try:
        seed_past_incidents()
        logger.info("💾 Past incidents seeded into ChromaDB")
    except Exception as e:
        logger.warning(f"⚠️ Failed to seed past incidents: {e}")

    yield
    logger.info("🛑 Vigil API shutting down...")


# ─── App ───
app = FastAPI(
    title="Vigil — Incident Response Agent",
    description="Autonomous AI incident response system",
    version="0.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Dashboard ───
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the real-time dashboard."""
    html_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    return FileResponse(html_path, media_type="text/html")


# ─── WebSocket ───
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket for real-time incident updates to the dashboard."""
    await ws.accept()
    events.register(ws)
    try:
        while True:
            await ws.receive_text()  # Keep connection alive
    except WebSocketDisconnect:
        events.unregister(ws)


# ─── Health ───
@app.get("/health")
async def health():
    return {"status": "healthy", "service": "vigil-api", "incidents_count": len(incidents)}


# ─── Receive Alertmanager Webhook ───
@app.post("/incident")
async def receive_alert(request: Request):
    """
    Receives Alertmanager webhook payload.
    Deduplicates and triggers investigation.
    """
    payload = await request.json()
    logger.info("📨 Received alert webhook")

    created_incidents = []

    alerts = payload.get("alerts", [])
    if not alerts:
        alerts = [payload]

    for alert in alerts:
        labels = alert.get("labels", {})
        annotations = alert.get("annotations", {})
        status = alert.get("status", "firing")

        alert_name = labels.get("alertname", "UnknownAlert")
        service = labels.get("service", "unknown")

        if status == "resolved":
            dedup_key = f"{alert_name}:{service}"
            _active_alerts.pop(dedup_key, None)
            logger.info(f"✅ Resolved alert cleared: {alert_name} on {service}")
            continue

        dedup_key = f"{alert_name}:{service}"
        if dedup_key in _active_alerts:
            existing_id = _active_alerts[dedup_key]
            logger.info(f"⏭️ Skipping duplicate: {alert_name} on {service} (incident {existing_id})")
            continue

        incident_id = str(uuid.uuid4())[:8]
        severity = labels.get("severity", "warning")
        summary = annotations.get("summary", alert_name)

        incident = Incident(
            id=incident_id,
            title=summary,
            severity=severity,
            service=service,
            raw_alert=alert,
            status=IncidentStatus.RECEIVED,
            created_at=datetime.utcnow(),
        )

        incidents[incident_id] = incident
        _active_alerts[dedup_key] = incident_id
        logger.info(f"🚨 INCIDENT CREATED [{incident_id}] severity={severity} service={service} title={summary}")

        created_incidents.append({
            "id": incident_id, "title": summary, "severity": severity,
            "service": service, "status": incident.status.value,
        })

        # Emit creation event to dashboard
        await events.emit(incident_id, "incident_created", {
            "title": summary, "severity": severity,
            "service": service, "status": "received",
        })

        asyncio.create_task(_run_investigation(incident_id))

    return JSONResponse(status_code=200, content={
        "status": "received", "incidents_created": len(created_incidents), "incidents": created_incidents,
    })


async def _run_investigation(incident_id: str):
    """Background task: run the full AI investigation pipeline with live events."""
    incident = incidents.get(incident_id)
    if not incident:
        return

    # Event callback for the orchestrator to emit tool progress
    async def on_event(event_type: str, data: dict):
        await events.emit(incident_id, event_type, data)

    try:
        # Step 1: Investigating
        incident.status = IncidentStatus.INVESTIGATING
        await events.emit(incident_id, "status_changed", {"status": "investigating"})
        logger.info(f"🔍 [{incident_id}] Starting AI investigation...")

        findings = await investigate(incident, on_event=on_event)
        incident.findings = findings
        logger.info(f"✅ [{incident_id}] Investigation complete: {findings.root_cause}")

        # Emit findings to dashboard
        await events.emit(incident_id, "findings_ready", {
            "root_cause": findings.root_cause,
            "started_at": findings.started_at,
            "last_commit": findings.last_commit,
            "runbook_match": findings.runbook_match,
            "past_similar": findings.past_similar,
            "is_recurring": findings.is_recurring,
            "recurrence_count": findings.recurrence_count,
        })

        # Step 2: Generate briefing
        briefing = await generate_briefing(incident)
        incident.briefing_script = briefing
        logger.info(f"🎤 [{incident_id}] Briefing generated: {briefing[:100]}...")

        await events.emit(incident_id, "briefing_ready", {"briefing": briefing})

        # Step 3: Ready to call
        incident.status = IncidentStatus.CALLING
        await events.emit(incident_id, "status_changed", {"status": "calling"})
        logger.info(f"📞 [{incident_id}] Investigation complete. Ready to call on-call engineer.")

    except Exception as e:
        logger.error(f"❌ [{incident_id}] Investigation pipeline failed: {e}")
        if not incident.findings:
            incident.findings = IncidentFindings(root_cause=f"Investigation failed: {e}")


# ─── Get Incident by ID ───
@app.get("/incident/{incident_id}")
async def get_incident(incident_id: str):
    incident = incidents.get(incident_id)
    if not incident:
        return JSONResponse(status_code=404, content={"error": "Incident not found"})
    return incident.model_dump(mode="json")


# ─── List All Incidents ───
@app.get("/incidents")
async def list_incidents():
    return [
        {
            "id": inc.id, "title": inc.title, "severity": inc.severity,
            "service": inc.service, "status": inc.status.value,
            "created_at": inc.created_at.isoformat(),
            "has_findings": inc.findings is not None,
            "briefing": inc.briefing_script[:100] + "..." if inc.briefing_script else None,
        }
        for inc in sorted(incidents.values(), key=lambda x: x.created_at, reverse=True)
    ]


# ─── Manual trigger for testing ───
@app.post("/test/trigger")
async def test_trigger(request: Request):
    """Manual trigger for testing without Alertmanager."""
    body = await request.json()
    incident_id = str(uuid.uuid4())[:8]

    incident = Incident(
        id=incident_id,
        title=body.get("title", "Test incident"),
        severity=body.get("severity", "critical"),
        service=body.get("service", "flask-app"),
        raw_alert=body,
        status=IncidentStatus.RECEIVED,
        created_at=datetime.utcnow(),
    )

    incidents[incident_id] = incident
    logger.info(f"🧪 TEST INCIDENT [{incident_id}]: {incident.title}")

    # Emit creation event to dashboard
    await events.emit(incident_id, "incident_created", {
        "title": incident.title, "severity": incident.severity,
        "service": incident.service, "status": "received",
    })

    asyncio.create_task(_run_investigation(incident_id))

    return {"status": "triggered", "incident_id": incident_id}
