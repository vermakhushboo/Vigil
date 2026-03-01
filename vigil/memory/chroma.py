"""Vigil — Shared ChromaDB client.

Single ChromaDB client and embedding function shared across all modules.
Prevents multiple client instances, SQLite lock contention, and
redundant embedding model loads.
"""
import os

import chromadb
from chromadb.utils import embedding_functions

CHROMA_DIR = os.environ.get("CHROMA_PERSIST_DIR", "./chroma_db")

# ─── Singleton instances ───
_client = None
_embedding_fn = None


def get_client() -> chromadb.PersistentClient:
    """Get the shared ChromaDB PersistentClient (singleton)."""
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=CHROMA_DIR)
    return _client


def get_embedding_fn():
    """Get the shared SentenceTransformer embedding function (singleton)."""
    global _embedding_fn
    if _embedding_fn is None:
        _embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
    return _embedding_fn


def get_collection(name: str, **kwargs):
    """Get or create a named collection with shared client + embedding fn."""
    return get_client().get_or_create_collection(
        name=name,
        embedding_function=get_embedding_fn(),
        **kwargs,
    )
