"""Vigil — Past incident similarity search tool.

Searches ChromaDB for historically similar incidents
and returns how they were resolved.
"""
import logging

import chromadb
from chromadb.utils import embedding_functions

logger = logging.getLogger("vigil.tools.incident_search")

CHROMA_DIR = "./chroma_db"

_chroma_client = None
_collection = None


def _get_collection():
    """Get or initialize the past_incidents ChromaDB collection."""
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
        metadata={"description": "Resolved past incidents for similarity matching"},
    )

    return _collection


def search_past_incidents(query: str) -> str:
    """
    Search historical incidents to find similar past events and resolutions.

    Args:
        query: Incident description to find similar past incidents.

    Returns:
        Formatted string of similar past incidents with resolutions.
    """
    logger.info(f"🔎 Searching past incidents: '{query}'")

    try:
        collection = _get_collection()

        if collection.count() == 0:
            return "No past incidents in memory. This appears to be a new type of incident."

        results = collection.query(
            query_texts=[query],
            n_results=3,
        )

        if not results["documents"] or not results["documents"][0]:
            return "No similar past incidents found."

        formatted = f"Found {len(results['documents'][0])} similar past incidents:\n\n"
        for i, (doc, metadata) in enumerate(
            zip(results["documents"][0], results["metadatas"][0])
        ):
            service = metadata.get("service", "unknown")
            severity = metadata.get("severity", "unknown")
            resolved_at = metadata.get("resolved_at", "unknown")
            formatted += (
                f"--- Past Incident #{i+1} (service: {service}, severity: {severity}) ---\n"
                f"{doc}\n"
                f"Resolved: {resolved_at}\n\n"
            )

        return formatted

    except Exception as e:
        logger.error(f"Past incident search failed: {e}")
        return f"Error searching past incidents: {e}"
