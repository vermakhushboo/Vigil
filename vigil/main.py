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

from vigil.config import settings, get_async_llm_client, MODEL_SMALL, AUDIO_DIR
from vigil.models.incident import Incident, IncidentStatus, IncidentFindings
from vigil.agents.orchestrator import investigate
from vigil.agents.synthesiser import generate_briefing
from vigil.tools.runbook_search import load_runbooks
from vigil.voice.tts import generate_audio
from vigil.voice.vapi import trigger_outbound_call
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

# Mount static files for serving TTS audio
AUDIO_DIR.mkdir(parents=True, exist_ok=True)  # ensure dir exists before mount
app.mount("/static", StaticFiles(directory=str(AUDIO_DIR.parent)), name="static")

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

        # Step 3: Convert briefing to audio (ElevenLabs TTS)
        audio_url = await generate_audio(incident_id, briefing)
        if audio_url:
            incident.briefing_audio_url = audio_url
            logger.info(f"🔊 [{incident_id}] Audio ready: {audio_url}")
            await events.emit(incident_id, "audio_ready", {"audio_url": audio_url})
        else:
            logger.info(f"🔇 [{incident_id}] TTS skipped (no API key or generation failed)")

        # Step 4: Ready to call
        incident.status = IncidentStatus.CALLING
        await events.emit(incident_id, "status_changed", {"status": "calling"})
        logger.info(f"📞 [{incident_id}] Investigation complete. Ready to call on-call engineer.")

        # Step 5: Trigger Vapi Phone Call
        call_success = await trigger_outbound_call(incident)
        if call_success:
            await events.emit(incident_id, "call_initiated", {"phone_number": settings.oncall_phone_number})

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


# ─── Q&A: Ask follow-up questions about an incident ───
@app.post("/incident/{incident_id}/ask")
async def ask_about_incident(incident_id: str, request: Request):
    """
    Ask a follow-up question about an incident in plain English.
    The agent answers using the full investigation context.
    """
    incident = incidents.get(incident_id)
    if not incident:
        return JSONResponse(status_code=404, content={"error": "Incident not found"})

    body = await request.json()
    question = body.get("question", "")
    if not question:
        return JSONResponse(status_code=400, content={"error": "No question provided"})

    if not settings.mistral_api_key:
        return JSONResponse(status_code=503, content={"error": "MISTRAL_API_KEY not configured"})

    # Build context from investigation
    findings = incident.findings
    context = (
        f"INCIDENT DETAILS:\n"
        f"  Title: {incident.title}\n"
        f"  Severity: {incident.severity}\n"
        f"  Service: {incident.service}\n"
        f"  Status: {incident.status.value}\n"
        f"  Created: {incident.created_at.isoformat()}\n\n"
    )

    if findings:
        context += (
            f"INVESTIGATION FINDINGS:\n"
            f"  Root Cause: {findings.root_cause or 'Not determined'}\n"
            f"  Started At: {findings.started_at or 'Unknown'}\n"
            f"  Suspicious Commit: {findings.last_commit or 'None found'}\n"
            f"  Runbook Match: {findings.runbook_match or 'No matching runbook'}\n"
            f"  Similar Past Incidents: {findings.past_similar or 'None found'}\n"
            f"  Recurring: {'Yes (' + str(findings.recurrence_count) + ' times)' if findings.is_recurring else 'No'}\n\n"
        )

    if incident.briefing_script:
        context += f"BRIEFING:\n  {incident.briefing_script}\n\n"

    # Build conversation messages
    system_msg = (
        "You are Vigil, an AI incident response agent. You have just finished investigating "
        "a production incident. Answer the on-call engineer's questions using the investigation "
        "context below. Be direct, specific, and actionable. If you don't know something, say so.\n\n"
        f"{context}"
    )

    messages = [{"role": "system", "content": system_msg}]

    # Include last 10 Q&A exchanges (bounded to prevent context window overflow)
    history = incident.call_transcript[-10:]
    for entry in history:
        messages.append({"role": "user", "content": entry.get("question", "")})
        messages.append({"role": "assistant", "content": entry.get("answer", "")})

    messages.append({"role": "user", "content": question})

    try:
        client = get_async_llm_client()

        response = await client.chat.completions.create(
            model=MODEL_SMALL,
            messages=messages,
        )

        answer = response.choices[0].message.content
        logger.info(f"💬 [{incident_id}] Q: {question[:60]}... A: {answer[:60]}...")

        # Save to transcript for conversation continuity
        incident.call_transcript.append({
            "question": question,
            "answer": answer,
            "timestamp": datetime.utcnow().isoformat(),
        })

        return {
            "incident_id": incident_id,
            "question": question,
            "answer": answer,
            "conversation_length": len(incident.call_transcript),
        }

    except Exception as e:
        logger.error(f"❌ [{incident_id}] Q&A failed: {e}")
        return JSONResponse(status_code=500, content={"error": f"Q&A failed: {e}"})

