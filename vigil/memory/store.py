"""Vigil — Store resolved incidents in ChromaDB."""
import logging

import chromadb
from chromadb.utils import embedding_functions

logger = logging.getLogger("vigil.memory.store")

CHROMA_DIR = "./chroma_db"

_chroma_client = None
_collection = None


def _get_collection():
    """Get or initialize the past_incidents collection."""
    global _chroma_client, _collection
    if _collection is not None:
        return _collection

    _chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    _collection = _chroma_client.get_or_create_collection(
        name="past_incidents",
        embedding_function=ef,
    )
    return _collection


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
