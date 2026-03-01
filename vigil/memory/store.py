"""Vigil — Store resolved incidents in ChromaDB."""
import logging

from vigil.memory.chroma import get_collection

logger = logging.getLogger("vigil.memory.store")


def _get_collection():
    return get_collection("past_incidents")


def store_incident(incident) -> None:
    """
    Store a resolved incident in ChromaDB for future similarity matching.
    Called after the engineer confirms resolution.
    """
    collection = _get_collection()

    root_cause = ""
    last_commit = ""
    if incident.findings:
        root_cause = incident.findings.root_cause or "Unknown"
        last_commit = incident.findings.last_commit or "None"

    resolution = incident.resolution or "No resolution recorded"

    text = (
        f"Title: {incident.title}\n"
        f"Service: {incident.service}\n"
        f"Severity: {incident.severity}\n"
        f"Root Cause: {root_cause}\n"
        f"Last Commit: {last_commit}\n"
        f"Resolution: {resolution}\n"
    )

    metadata = {
        "service": incident.service,
        "severity": incident.severity,
        "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else "unknown",
        "title": incident.title,
    }

    collection.add(
        documents=[text],
        ids=[incident.id],
        metadatas=[metadata],
    )
    logger.info(f"💾 Stored resolved incident [{incident.id}] in memory")
