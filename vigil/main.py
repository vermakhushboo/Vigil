"""Vigil — FastAPI entrypoint.

Receives Alertmanager webhooks, creates Incident objects,
and triggers the AI agent investigation pipeline.
"""
import uuid
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from vigil.config import settings
from vigil.models.incident import Incident, IncidentStatus, IncidentFindings
from vigil.agents.orchestrator import investigate
from vigil.agents.synthesiser import generate_briefing
from vigil.tools.runbook_search import load_runbooks
from vigil.memory.seed import seed_past_incidents

# ─── Logging ───
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("vigil")

# ─── In-memory incident store ───
incidents: Dict[str, Incident] = {}

# ─── Deduplication: track active alerts by (alertname, service) ───
_active_alerts: Dict[str, str] = {}  # key: "alertname:service" → value: incident_id


# ─── Lifespan (replaces deprecated on_event) ───
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

    yield  # App runs here

    logger.info("🛑 Vigil API shutting down...")


# ─── App ───
app = FastAPI(
    title="Vigil — Incident Response Agent",
    description="Autonomous AI incident response system",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Health ───
@app.get("/health")
async def health():
    return {"status": "healthy", "service": "vigil-api", "incidents_count": len(incidents)}


# ─── Receive Alertmanager Webhook ───
@app.post("/incident")
async def receive_alert(request: Request):
    """
    Receives Alertmanager webhook payload.
    Parses alerts, creates Incident objects, and triggers investigation.
    Deduplicates: skips if an active incident already exists for this alert.
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

        # Skip resolved alerts
        if status == "resolved":
            dedup_key = f"{alert_name}:{service}"
            _active_alerts.pop(dedup_key, None)
            logger.info(f"✅ Resolved alert cleared: {alert_name} on {service}")
            continue

        # Deduplicate: skip if already investigating this alert
        dedup_key = f"{alert_name}:{service}"
        if dedup_key in _active_alerts:
            existing_id = _active_alerts[dedup_key]
            logger.info(f"⏭️ Skipping duplicate alert: {alert_name} on {service} (incident {existing_id} already active)")
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
        logger.info(
            f"🚨 INCIDENT CREATED [{incident_id}] "
            f"severity={severity} service={service} title={summary}"
        )
        created_incidents.append({
            "id": incident_id,
            "title": summary,
            "severity": severity,
            "service": service,
            "status": incident.status.value,
        })

        # 🤖 Trigger AI investigation as background task
        asyncio.create_task(_run_investigation(incident_id))

    return JSONResponse(
        status_code=200,
        content={
            "status": "received",
            "incidents_created": len(created_incidents),
            "incidents": created_incidents,
        },
    )


async def _run_investigation(incident_id: str):
    """Background task: run the full AI investigation pipeline."""
    incident = incidents.get(incident_id)
    if not incident:
        return

    try:
        # Step 1: Investigating
        incident.status = IncidentStatus.INVESTIGATING
        logger.info(f"🔍 [{incident_id}] Starting AI investigation...")

        findings = await investigate(incident)
        incident.findings = findings
        logger.info(f"✅ [{incident_id}] Investigation complete: {findings.root_cause}")

        # Step 2: Generate briefing
        briefing = await generate_briefing(incident)
        incident.briefing_script = briefing
        logger.info(f"🎤 [{incident_id}] Briefing generated: {briefing[:100]}...")

        # Step 3: Ready to call (Phase 4 will trigger Twilio here)
        incident.status = IncidentStatus.CALLING
        logger.info(
            f"📞 [{incident_id}] Investigation complete. Ready to call on-call engineer.\n"
            f"    Briefing: {briefing}"
        )

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
            "id": inc.id,
            "title": inc.title,
            "severity": inc.severity,
            "service": inc.service,
            "status": inc.status.value,
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

    asyncio.create_task(_run_investigation(incident_id))

    return {"status": "triggered", "incident_id": incident_id}
