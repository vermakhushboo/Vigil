"""Vigil — Retrieve similar past incidents from ChromaDB."""
import logging

import chromadb
from chromadb.utils import embedding_functions

logger = logging.getLogger("vigil.memory.retrieve")

CHROMA_DIR = "./chroma_db"

_chroma_client = None
_collection = None


def _get_collection():
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
    """Count how many past incidents match a given service + similar title (pattern detection)."""
    collection = _get_collection()
    if collection.count() == 0:
        return 0

    results = collection.query(
        query_texts=[f"{service} {title}"],
        n_results=10,
        where={"service": service},
    )

    return len(results["documents"][0]) if results["documents"] and results["documents"][0] else 0
