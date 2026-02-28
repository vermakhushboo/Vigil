"""Vigil — FastAPI entrypoint.

Receives Alertmanager webhooks, creates Incident objects,
and will trigger the AI agent pipeline in later phases.
"""
import uuid
import logging
from datetime import datetime
from typing import Dict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from vigil.config import settings
from vigil.models.incident import Incident, IncidentStatus

# ─── Logging ───
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("vigil")

# ─── App ───
app = FastAPI(
    title="Vigil — Incident Response Agent",
    description="Autonomous AI incident response system",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── In-memory incident store ───
incidents: Dict[str, Incident] = {}


# ─── Health ───
@app.get("/health")
async def health():
    return {"status": "healthy", "service": "vigil-api", "incidents_count": len(incidents)}


# ─── Receive Alertmanager Webhook ───
@app.post("/incident")
async def receive_alert(request: Request):
    """
    Receives Alertmanager webhook payload.
    Parses alerts, creates Incident objects, and logs them.
    In later phases, this will trigger the AI investigation pipeline.
    """
    payload = await request.json()
    logger.info(f"📨 Received alert webhook: {payload}")

    created_incidents = []

    alerts = payload.get("alerts", [])
    if not alerts:
        # Handle case where payload IS the alert (manual trigger)
        alerts = [payload]

    for alert in alerts:
        labels = alert.get("labels", {})
        annotations = alert.get("annotations", {})
        status = alert.get("status", "firing")

        # Skip resolved alerts for now
        if status == "resolved":
            logger.info(f"✅ Received resolved alert: {labels.get('alertname', 'unknown')}")
            continue

        incident_id = str(uuid.uuid4())[:8]
        alert_name = labels.get("alertname", "UnknownAlert")
        severity = labels.get("severity", "warning")
        service = labels.get("service", "unknown")
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

        # TODO (Phase 2): Trigger AI agent investigation pipeline here
        # asyncio.create_task(investigate(incident))

    return JSONResponse(
        status_code=200,
        content={
            "status": "received",
            "incidents_created": len(created_incidents),
            "incidents": created_incidents,
        },
    )


# ─── Get Incident by ID ───
@app.get("/incident/{incident_id}")
async def get_incident(incident_id: str):
    incident = incidents.get(incident_id)
    if not incident:
        return JSONResponse(status_code=404, content={"error": "Incident not found"})
    return incident.model_dump()


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
        }
        for inc in sorted(incidents.values(), key=lambda x: x.created_at, reverse=True)
    ]
