"""Vigil — Synthesiser Agent (via NVIDIA API).

Takes the orchestrator's findings and generates a concise
30-second voice briefing script for the on-call engineer.

Uses NVIDIA's OpenAI-compatible API endpoint to access Mistral models.
"""
import logging

from openai import AsyncOpenAI

from vigil.config import settings, get_async_llm_client, MODEL_SMALL
from vigil.models.incident import Incident

logger = logging.getLogger("vigil.agents.synthesiser")

SYSTEM_PROMPT = """Convert this incident investigation into a clear, spoken briefing for an on-call engineer.
Rules:
- Max 4 sentences
- Start with severity and service affected
- Include the most likely cause
- End with the recommended first action
- Write for spoken audio, not reading. No bullet points, no markdown.
- Be direct and confident. Engineers want facts, not hedging.
"""


async def generate_briefing(incident: Incident) -> str:
    """
    Generate a 30-second voice briefing from investigation findings.

    Uses mistral-small-latest for faster/cheaper generation.
    """
    if not settings.mistral_api_key:
        logger.error("❌ MISTRAL_API_KEY not set")
        return _fallback_briefing(incident)

    if not incident.findings:
        return _fallback_briefing(incident)

    findings = incident.findings
    context = (
        f"Incident: {incident.title}\n"
        f"Severity: {incident.severity}\n"
        f"Service: {incident.service}\n"
        f"Root Cause: {findings.root_cause or 'Unknown'}\n"
        f"Started At: {findings.started_at or 'Unknown'}\n"
        f"Suspicious Commit: {findings.last_commit or 'None found'}\n"
        f"Runbook: {findings.runbook_match or 'No matching runbook'}\n"
        f"Past Similar: {findings.past_similar or 'No similar past incidents'}\n"
        f"Recurring: {'Yes, seen ' + str(findings.recurrence_count) + ' times before' if findings.is_recurring else 'No'}\n"
    )

    try:
        client = get_async_llm_client()
        response = await client.chat.completions.create(
            model=MODEL_SMALL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": context},
            ],
        )
        briefing = response.choices[0].message.content
        logger.info(f"🎤 Briefing generated: {briefing[:100]}...")
        return briefing

    except Exception as e:
        logger.error(f"❌ Synthesiser failed: {e}")
        return _fallback_briefing(incident)


def _fallback_briefing(incident: Incident) -> str:
    """Generate a simple fallback briefing without Mistral."""
    root_cause = "unknown cause"
    if incident.findings and incident.findings.root_cause:
        root_cause = incident.findings.root_cause

    return (
        f"Critical alert on {incident.service}. "
        f"{incident.title}. "
        f"The most likely cause is {root_cause}. "
        f"Please check the service status and recent deployments immediately."
    )
