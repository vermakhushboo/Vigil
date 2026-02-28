"""Vigil — Seed ChromaDB with past incidents for demo.

Pre-populates the past_incidents collection with realistic
resolved incidents so the agent can find similar patterns.
"""
import logging

import chromadb
from chromadb.utils import embedding_functions

logger = logging.getLogger("vigil.memory.seed")

CHROMA_DIR = "./chroma_db"

SEED_INCIDENTS = [
    {
        "id": "seed-001",
        "text": (
            "Title: High 5xx error rate on flask-app\n"
            "Service: flask-app\n"
            "Severity: critical\n"
            "Root Cause: A bad deploy introduced a null pointer exception in the error handling middleware. "
            "The middleware was crashing on every request that contained a malformed JSON body.\n"
            "Last Commit: fix: update error handler middleware (sha: abc123)\n"
            "Resolution: Rolled back to previous version. Fixed the null check in error handler and redeployed."
        ),
        "metadata": {
            "service": "flask-app",
            "severity": "critical",
            "resolved_at": "2025-02-15T10:30:00Z",
            "title": "High 5xx error rate on flask-app",
        },
    },
    {
        "id": "seed-002",
        "text": (
            "Title: PostgreSQL database connection failure\n"
            "Service: postgres\n"
            "Severity: critical\n"
            "Root Cause: The PostgreSQL container ran out of shared memory due to too many idle connections "
            "from the connection pool. The pool was misconfigured after a recent config change.\n"
            "Last Commit: refactor: update connection pool settings (sha: def456)\n"
            "Resolution: Restarted PostgreSQL, reduced max_connections in pool config from 100 to 25. "
            "Added connection timeout of 30s."
        ),
        "metadata": {
            "service": "postgres",
            "severity": "critical",
            "resolved_at": "2025-02-10T03:45:00Z",
            "title": "PostgreSQL database connection failure",
        },
    },
    {
        "id": "seed-003",
        "text": (
            "Title: CPU spike on flask-app causing high latency\n"
            "Service: flask-app\n"
            "Severity: warning\n"
            "Root Cause: A new data validation endpoint was performing regex matching on large payloads "
            "without input size limits, causing exponential CPU usage.\n"
            "Last Commit: feat: add input validation for /api/upload (sha: ghi789)\n"
            "Resolution: Added a 1MB input size limit and moved regex validation to an async worker. "
            "Latency returned to normal within 2 minutes."
        ),
        "metadata": {
            "service": "flask-app",
            "severity": "warning",
            "resolved_at": "2025-02-20T14:20:00Z",
            "title": "CPU spike on flask-app causing high latency",
        },
    },
    {
        "id": "seed-004",
        "text": (
            "Title: PostgreSQL database unreachable after config change\n"
            "Service: postgres\n"
            "Severity: critical\n"
            "Root Cause: A change to pg_hba.conf accidentally removed the entry allowing connections "
            "from the Flask app's subnet. All database queries started failing with 'connection refused'.\n"
            "Last Commit: chore: update postgres auth config (sha: jkl012)\n"
            "Resolution: Reverted pg_hba.conf change and reloaded PostgreSQL config. Added a CI check "
            "to validate pg_hba.conf format before merging."
        ),
        "metadata": {
            "service": "postgres",
            "severity": "critical",
            "resolved_at": "2025-01-28T22:15:00Z",
            "title": "PostgreSQL database unreachable after config change",
        },
    },
    {
        "id": "seed-005",
        "text": (
            "Title: Intermittent 500 errors on API endpoints\n"
            "Service: flask-app\n"
            "Severity: warning\n"
            "Root Cause: A race condition in the session middleware was causing occasional crashes "
            "when two requests arrived simultaneously for the same user session.\n"
            "Last Commit: fix: add mutex lock to session handler (sha: mno345)\n"
            "Resolution: Added thread-safe locking to the session manager. Deployed hotfix and "
            "monitored for 30 minutes — no recurrence."
        ),
        "metadata": {
            "service": "flask-app",
            "severity": "warning",
            "resolved_at": "2025-02-25T08:50:00Z",
            "title": "Intermittent 500 errors on API endpoints",
        },
    },
    {
        "id": "seed-006",
        "text": (
            "Title: Database connection pool exhaustion causing service outage\n"
            "Service: postgres\n"
            "Severity: critical\n"
            "Root Cause: A memory leak in the ORM layer was holding database connections open indefinitely. "
            "After 2 hours of traffic, all 50 pool connections were consumed.\n"
            "Last Commit: fix: ensure DB connections are released in finally block (sha: pqr678)\n"
            "Resolution: Restarted the application to release all connections. Fixed the connection "
            "leak by adding proper context managers. Added connection pool monitoring alert."
        ),
        "metadata": {
            "service": "postgres",
            "severity": "critical",
            "resolved_at": "2025-02-05T16:30:00Z",
            "title": "Database connection pool exhaustion causing service outage",
        },
    },
]


def seed_past_incidents():
    """Seed ChromaDB with past incidents for demo purposes."""
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    collection = client.get_or_create_collection(
        name="past_incidents",
        embedding_function=ef,
    )

    # Check if already seeded
    existing = collection.get(ids=[s["id"] for s in SEED_INCIDENTS])
    already_seeded = len([i for i in existing["ids"] if i]) if existing["ids"] else 0

    if already_seeded >= len(SEED_INCIDENTS):
        logger.info(f"💾 Past incidents already seeded ({already_seeded} incidents)")
        return

    # Add only missing incidents
    for seed in SEED_INCIDENTS:
        if seed["id"] not in (existing["ids"] or []):
            collection.add(
                documents=[seed["text"]],
                ids=[seed["id"]],
                metadatas=[seed["metadata"]],
            )

    logger.info(f"💾 Seeded {len(SEED_INCIDENTS)} past incidents into ChromaDB")
