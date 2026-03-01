"""Vigil — Retrieve similar past incidents from ChromaDB."""
import logging

from vigil.memory.chroma import get_collection

logger = logging.getLogger("vigil.memory.retrieve")


def _get_collection():
    return get_collection("past_incidents")


def find_similar_incidents(query: str, top_k: int = 3) -> list:
    """Return top-k similar past incidents as a list of dicts."""
    collection = _get_collection()

    if collection.count() == 0:
        return []

    results = collection.query(query_texts=[query], n_results=top_k)

    incidents = []
    for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
        incidents.append({"text": doc, "metadata": meta})
    return incidents


def count_similar(service: str, title: str) -> int:
    """Count how many past incidents match a given service + similar title."""
    collection = _get_collection()
    if collection.count() == 0:
        return 0

    results = collection.query(
        query_texts=[f"{service} {title}"],
        n_results=10,
        where={"service": service},
    )

    return len(results["documents"][0]) if results["documents"] and results["documents"][0] else 0
