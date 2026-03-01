"""Vigil — Runbook search tool (ChromaDB RAG).

Embeds and searches internal runbook markdown files
using ChromaDB with sentence-transformer embeddings.
"""
import logging
import os
import glob

from vigil.memory.chroma import get_collection

logger = logging.getLogger("vigil.tools.runbook_search")

RUNBOOKS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "runbooks")


def _get_collection():
    """Get the runbooks ChromaDB collection (shared client)."""
    return get_collection(
        "runbooks",
        metadata={"description": "Internal runbook documents for incident remediation"},
    )


def load_runbooks():
    """Load all runbook markdown files into ChromaDB."""
    collection = _get_collection()

    # Check if already loaded
    if collection.count() > 0:
        logger.info(f"📚 Runbooks already loaded ({collection.count()} chunks)")
        return

    runbook_files = glob.glob(os.path.join(RUNBOOKS_DIR, "*.md"))
    if not runbook_files:
        logger.warning(f"No runbook files found in {RUNBOOKS_DIR}")
        return

    documents = []
    metadatas = []
    ids = []

    for filepath in runbook_files:
        filename = os.path.basename(filepath)
        with open(filepath, "r") as f:
            content = f.read()

        # Split into chunks by section (## headers)
        sections = content.split("\n## ")
        for i, section in enumerate(sections):
            if i == 0:
                chunk_text = section.strip()
            else:
                chunk_text = f"## {section.strip()}"

            if len(chunk_text) < 20:
                continue

            chunk_id = f"{filename}__chunk_{i}"
            documents.append(chunk_text)
            metadatas.append({
                "source": filename,
                "chunk_index": i,
                "type": "runbook",
            })
            ids.append(chunk_id)

    if documents:
        collection.add(documents=documents, metadatas=metadatas, ids=ids)
        logger.info(f"📚 Loaded {len(documents)} runbook chunks from {len(runbook_files)} files")


def search_runbooks(query: str) -> str:
    """
    Search internal runbooks for remediation steps matching the query.

    Args:
        query: Incident description to match against runbooks.

    Returns:
        The most relevant runbook content, or a message if none found.
    """
    logger.info(f"📖 Searching runbooks: '{query}'")

    try:
        collection = _get_collection()

        if collection.count() == 0:
            load_runbooks()

        if collection.count() == 0:
            return "No runbooks are loaded. Cannot search for remediation steps."

        results = collection.query(
            query_texts=[query],
            n_results=3,
        )

        if not results["documents"] or not results["documents"][0]:
            return f"No runbook matches found for: '{query}'"

        formatted = "Relevant runbook sections:\n\n"
        for doc, metadata in zip(results["documents"][0], results["metadatas"][0]):
            source = metadata.get("source", "unknown")
            formatted += f"--- From {source} ---\n{doc}\n\n"

        return formatted

    except Exception as e:
        logger.error(f"Runbook search failed: {e}")
        return f"Error searching runbooks: {e}"
