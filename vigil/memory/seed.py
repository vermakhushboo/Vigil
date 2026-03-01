"""Vigil — Seed ChromaDB with past incidents for demo.

Pre-populates the past_incidents collection with realistic
resolved incidents so the agent can find similar patterns.
Each incident has detailed resolution steps and impact metrics.
"""
import logging

from vigil.memory.chroma import get_collection

logger = logging.getLogger("vigil.memory.seed")

SEED_INCIDENTS = [
    # ─── 5xx Error Scenarios ───
    {
        "id": "seed-001",
        "text": (
            "Title: High 5xx error rate on flask-app\n"
            "Service: flask-app\n"
            "Severity: critical\n"
            "Root Cause: A deployment introduced a null pointer exception in error_handler.py line 42. "
            "The developer removed a null check on request.body during a refactor, causing the error "
            "handler middleware to crash with AttributeError on every request with a missing or "
            "malformed JSON body. Since the error handler itself was crashing, ALL routes returned "
            "HTTP 500 — including /health.\n"
            "Last Commit: fix: refactor error handler middleware (sha: abc123) by sarah.chen — "
            "changed error_handler.py, routes/api.py\n"
            "Resolution: Rolled back commit abc123 immediately. Then fixed the null check: added "
            "`if request.body is not None` guard before accessing request.body.get(). Added unit "
            "test for null body edge case. Redeployed and monitored — error rate dropped to 0 "
            "within 30 seconds of rollback.\n"
            "Duration: 8 minutes from alert to resolution\n"
            "Impact: 100% of API requests failed for 8 minutes. ~2,400 failed requests."
        ),
        "metadata": {
            "service": "flask-app",
            "severity": "critical",
            "resolved_at": "2025-02-15T10:30:00Z",
            "title": "High 5xx error rate on flask-app",
        },
    },
    {
        "id": "seed-005",
        "text": (
            "Title: Intermittent 500 errors on API endpoints after deploy\n"
            "Service: flask-app\n"
            "Severity: warning\n"
            "Root Cause: A race condition in the session middleware was causing crashes when two "
            "requests arrived simultaneously for the same user session. The deploy changed the "
            "session handler from thread-safe to non-thread-safe implementation.\n"
            "Last Commit: fix: simplify session handler (sha: mno345) by sarah.chen — "
            "changed middleware/session_handler.py\n"
            "Resolution: Added thread-safe mutex lock to the session manager. Deployed hotfix "
            "within 15 minutes. Monitored for 30 minutes — no recurrence. Added concurrency "
            "tests to CI pipeline.\n"
            "Duration: 15 minutes from alert to fix deployed\n"
            "Impact: ~5% of requests affected (only concurrent same-session requests). ~120 failed requests."
        ),
        "metadata": {
            "service": "flask-app",
            "severity": "warning",
            "resolved_at": "2025-02-25T08:50:00Z",
            "title": "Intermittent 500 errors on API endpoints",
        },
    },

    # ─── Database / PostgreSQL Scenarios ───
    {
        "id": "seed-002",
        "text": (
            "Title: PostgreSQL database connection failure — pool exhaustion\n"
            "Service: postgres\n"
            "Severity: critical\n"
            "Root Cause: A config change increased max_connections from 25 to 100 in database.py, "
            "which exceeded PostgreSQL's shared_memory allocation. The container ran out of shared "
            "memory, causing new connections to fail with 'could not connect to server'. "
            "pg_up dropped to 0, triggering the PostgresDown alert.\n"
            "Last Commit: refactor: update connection pool settings (sha: def456) by james.wilson — "
            "changed config/database.py, docker-compose.yml\n"
            "Resolution: Reverted max_connections to 25 and added idle_timeout=30s to prevent "
            "connection hoarding. Restarted PostgreSQL container: `docker compose restart postgres`. "
            "Then restarted flask-app to re-establish the connection pool. Verified with pg_isready.\n"
            "Duration: 12 minutes from alert to resolution\n"
            "Impact: All database-dependent endpoints failed. ~1,800 failed requests across 12 minutes."
        ),
        "metadata": {
            "service": "postgres",
            "severity": "critical",
            "resolved_at": "2025-02-10T03:45:00Z",
            "title": "PostgreSQL database connection failure",
        },
    },
    {
        "id": "seed-004",
        "text": (
            "Title: PostgreSQL unreachable after pg_hba.conf change\n"
            "Service: postgres\n"
            "Severity: critical\n"
            "Root Cause: A change to pg_hba.conf accidentally removed the entry allowing connections "
            "from the flask-app subnet (172.18.0.0/16). All database queries immediately failed with "
            "'connection refused' (psycopg2.OperationalError). pg_isready returned 'no response'.\n"
            "Last Commit: chore: update postgres auth config (sha: jkl012) by alex.kumar — "
            "changed config/pg_hba.conf\n"
            "Resolution: Reverted pg_hba.conf to include `host all all 172.18.0.0/16 md5`. "
            "Reloaded PostgreSQL config without restart: `pg_ctl reload`. Added a CI check "
            "to validate pg_hba.conf format and ensure app subnet is always included.\n"
            "Duration: 6 minutes from alert to resolution\n"
            "Impact: Complete database outage for 6 minutes. All API endpoints returning 500."
        ),
        "metadata": {
            "service": "postgres",
            "severity": "critical",
            "resolved_at": "2025-01-28T22:15:00Z",
            "title": "PostgreSQL database unreachable after config change",
        },
    },
    {
        "id": "seed-006",
        "text": (
            "Title: Database connection pool exhaustion — ORM connection leak\n"
            "Service: postgres\n"
            "Severity: critical\n"
            "Root Cause: A memory leak in the ORM layer was holding database connections open "
            "indefinitely — missing `connection.close()` in a finally block. After 2 hours of "
            "traffic, all 50 pool connections were consumed. pg_isready still returned OK (PostgreSQL "
            "was running), but no application could get a connection.\n"
            "Last Commit: fix: ensure DB connections are released in finally block (sha: pqr678) "
            "by james.wilson — changed app/db/session.py\n"
            "Resolution: Restarted flask-app to release all leaked connections. Then fixed the "
            "connection leak by wrapping all DB operations in `try/finally` with explicit "
            "`connection.close()`. Added connection pool monitoring alert for when available "
            "connections drop below 5.\n"
            "Duration: 20 minutes from alert to resolution\n"
            "Impact: Gradual degradation over 2 hours, then complete outage for ~8 minutes."
        ),
        "metadata": {
            "service": "postgres",
            "severity": "critical",
            "resolved_at": "2025-02-05T16:30:00Z",
            "title": "Database connection pool exhaustion causing service outage",
        },
    },

    # ─── CPU Spike Scenarios ───
    {
        "id": "seed-003",
        "text": (
            "Title: CPU spike on flask-app — synchronous report generation\n"
            "Service: flask-app\n"
            "Severity: warning\n"
            "Root Cause: The /api/reports/generate endpoint was performing synchronous JSON "
            "serialization of a full dataset (50MB+) in the request handler thread. A single "
            "request to this endpoint consumed 95% CPU for 30 seconds, blocking all other "
            "requests. Worker process PID showed 97% CPU in data_processor.transform_batch().\n"
            "Last Commit: feat: add report generation endpoint (sha: ghi789) by alex.kumar — "
            "changed app/handlers/data_processor.py, routes/reports.py\n"
            "Resolution: Moved report generation to an async background worker using Celery. "
            "The endpoint now returns 202 Accepted with a job ID. Added a 10MB payload size "
            "limit. CPU returned to baseline (< 10%) within 2 minutes of deploying the fix.\n"
            "Duration: 25 minutes from alert to resolution\n"
            "Impact: Request latency p95 jumped from 120ms to 8.3s for all endpoints during spikes."
        ),
        "metadata": {
            "service": "flask-app",
            "severity": "warning",
            "resolved_at": "2025-02-20T14:20:00Z",
            "title": "CPU spike on flask-app causing high latency",
        },
    },
    {
        "id": "seed-007",
        "text": (
            "Title: CPU spike from regex backtracking on /api/validate\n"
            "Service: flask-app\n"
            "Severity: warning\n"
            "Root Cause: A complex regex pattern in the input validation endpoint caused exponential "
            "backtracking (ReDoS) on certain input strings. A single crafted request consumed 100% "
            "CPU for 45 seconds. Container health checks started failing at 4+ second response time.\n"
            "Last Commit: feat: add regex validation for email field (sha: stu901) by priya.patel — "
            "changed app/validation/schemas.py\n"
            "Resolution: Replaced the complex regex with a simpler pattern. Added a 1MB input "
            "size limit and a 5-second timeout on the validation endpoint. CPU dropped to baseline "
            "immediately after deploying the fix.\n"
            "Duration: 18 minutes from alert to resolution\n"
            "Impact: Intermittent — only triggered by specific input patterns. ~50 requests affected."
        ),
        "metadata": {
            "service": "flask-app",
            "severity": "warning",
            "resolved_at": "2025-02-22T11:00:00Z",
            "title": "CPU spike from regex backtracking",
        },
    },
]


def seed_past_incidents():
    """Seed ChromaDB with past incidents for demo purposes."""
    collection = get_collection("past_incidents")

    # Check if already seeded
    existing = collection.get(ids=[s["id"] for s in SEED_INCIDENTS])
    already_seeded = len([i for i in existing["ids"] if i]) if existing["ids"] else 0

    if already_seeded >= len(SEED_INCIDENTS):
        logger.info(f"💾 Past incidents already seeded ({already_seeded} incidents)")
        return

    # Add all incidents (replace if exists)
    for seed in SEED_INCIDENTS:
        if seed["id"] not in (existing["ids"] or []):
            collection.add(
                documents=[seed["text"]],
                ids=[seed["id"]],
                metadatas=[seed["metadata"]],
            )

    logger.info(f"💾 Seeded {len(SEED_INCIDENTS)} past incidents into ChromaDB")
