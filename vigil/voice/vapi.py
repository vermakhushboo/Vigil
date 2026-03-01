"""Vigil — Vapi.ai Integration for Outbound Voice Calls.

Triggers an outbound phone call using the Vapi REST API.
Overrides the assistant's system prompt with the specific incident
details (root cause, severity, etc.) so the AI can provide a 
customized, highly contextual briefing.
"""
import logging
import httpx

from vigil.config import settings
from vigil.models.incident import Incident

logger = logging.getLogger("vigil.voice.vapi")

VAPI_BASE_URL = "https://api.vapi.ai/call/phone"


def _build_system_prompt(incident: Incident) -> str:
    """Constructs the system prompt injected into the Vapi agent."""
    findings = incident.findings

    root_cause = findings.root_cause if findings else "Investigated but inconclusive."
    suspicious_commit = findings.last_commit if findings else "None"
    runbook_match = findings.runbook_match if findings else "None"
    recurrence_count = findings.recurrence_count if findings else 0

    return f"""You are Vigil, an autonomous Level-1 Site Reliability Engineering (SRE) AI agent. 
You are making an outbound phone call to the on-call engineer at 3:00 AM to wake them up and report a critical production incident that you have just finished investigating.

Your personality:
- Professional, urgent, concise, and calm.
- You speak like a senior engineer reporting facts to a colleague.
- You do not use filler words like "um", "ah", or "how are you today?".
- If you don't know the answer to a question, admit it directly—do not guess.

When the user picks up, immediately state who you are, the severity of the incident, and your primary finding in 3 sentences or less. Wait for them to acknowledge before continuing.

You have access to the following incident investigation context:

INCIDENT:
- Title: {incident.title}
- Service: {incident.service}
- Severity: {incident.severity}

FINDINGS:
- Root Cause: {root_cause}
- Suspicious Commit: {suspicious_commit}
- Runbook Match: {runbook_match}
- Past Incidents: This incident has occurred {recurrence_count} times before.

INSTRUCTIONS FOR THE CALL:
1. Wait for the user to speak first (e.g., they will say "Hello").
2. Then start by saying: "Hello, this is Vigil, your autonomous incident responder. I am calling regarding a {incident.severity} incident on {incident.service}. The root cause appears to be {root_cause}."
3. Pause and wait for the engineer to respond (e.g., "Go on" or "What's the fix?").
4. Answer their questions using ONLY the context provided above. 
5. If they ask for the remediation steps, read them the Runbook Match summary.
6. Keep all your responses under 15 seconds. If you have more to say, ask "Would you like me to elaborate?"
7. When the engineer says they are taking over or logging in, acknowledge them, say "Good luck, I am ending the call," and hang up.
"""


async def trigger_outbound_call(incident: Incident) -> bool:
    """
    Trigger an outbound phone call via Vapi to report an incident.
    Returns True if the call was successfully initiated.
    """
    if not settings.vapi_api_key:
        logger.warning("⚠️ VAPI_API_KEY not configured — skipping outbound voice call")
        return False

    if not settings.oncall_phone_number:
        logger.warning("⚠️ ONCALL_PHONE_NUMBER not configured — skipping outbound voice call")
        return False

    system_prompt = _build_system_prompt(incident)
    
    findings = incident.findings
    root_cause = findings.root_cause if findings else "anomaly detected"

    # Use firstMessage dynamically so the agent speaks as soon as the line connects 
    # (if configured to speak first, though usually Vapi waits for user's hello based on assistant config)
    first_message = (
        f"Hello, this is Vigil. I am calling regarding a {incident.severity} "
        f"incident on {incident.service}. The root cause appears to be: {root_cause}."
    )

    payload = {
        "phoneNumberId": settings.vapi_phone_number_id,
        "customer": {
            "number": settings.oncall_phone_number
        },
        "assistantId": settings.vapi_assistant_id,
        "assistantOverrides": {
            "model": {
                "messages": [
                    {
                        "role": "system",
                        "content": system_prompt
                    }
                ]
            },
            "firstMessage": first_message
        }
    }

    headers = {
        "Authorization": f"Bearer {settings.vapi_api_key}",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient() as client:
            logger.info(f"📞 [{incident.id}] Triggering Vapi phone call to {settings.oncall_phone_number}...")
            response = await client.post(VAPI_BASE_URL, json=payload, headers=headers, timeout=10.0)
            
            if response.status_code in (200, 201):
                data = response.json()
                logger.info(f"✅ [{incident.id}] Outbound call initiated. Vapi Call ID: {data.get('id')}")
                return True
            else:
                logger.error(f"❌ [{incident.id}] Vapi call failed: {response.status_code} - {response.text}")
                return False

    except Exception as e:
        logger.error(f"❌ [{incident.id}] Error triggering Vapi call: {e}")
        return False
