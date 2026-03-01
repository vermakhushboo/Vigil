"""Vigil — GitHub commits tool (seeded for hackathon demo).

Returns realistic hardcoded commits that correlate with each
chaos scenario. In production, this would call the GitHub API.

Commits are scenario-tagged so the agent sees a clear "guilty"
commit for each incident type alongside innocent recent changes.
"""
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("vigil.tools.github_finder")

# ─── Seeded commit history ───
# Each commit has a `scenario` tag so the guilty commit stands out.
# The agent sees ALL commits — the scenario tag is NOT exposed to it.
# The messages and file paths make the causal link obvious.

_COMMIT_TEMPLATES = [
    # ── 5xx scenario: "guilty" commit ──
    {
        "sha": "a1b2c3d",
        "message": "fix: refactor error handler middleware — removed null check on request.body to simplify code",
        "author": "sarah.chen",
        "minutes_ago": 12,
        "files_changed": [
            "app/middleware/error_handler.py",
            "app/routes/api.py",
            "tests/test_error_handler.py",
        ],
        "scenario": "5xx",
    },
    # ── DB scenario: "guilty" commit ──
    {
        "sha": "e4f5g6h",
        "message": "refactor: change DB connection pool max_connections from 25 to 100 and remove idle_timeout",
        "author": "james.wilson",
        "minutes_ago": 25,
        "files_changed": [
            "config/database.py",
            "docker-compose.yml",
            "config/postgresql.conf",
        ],
        "scenario": "db",
    },
    # ── Innocent commit ──
    {
        "sha": "i7j8k9l",
        "message": "feat: add input validation schemas for /api/orders endpoint",
        "author": "priya.patel",
        "minutes_ago": 45,
        "files_changed": [
            "app/validation/schemas.py",
            "app/middleware/validator.py",
        ],
        "scenario": "none",
    },
    # ── CPU scenario: "guilty" commit ──
    {
        "sha": "b3c4d5e",
        "message": "feat: add synchronous JSON serialization for /api/reports/generate — processes full dataset in memory",
        "author": "alex.kumar",
        "minutes_ago": 35,
        "files_changed": [
            "app/handlers/data_processor.py",
            "app/routes/reports.py",
        ],
        "scenario": "cpu",
    },
    # ── Innocent commits ──
    {
        "sha": "m0n1o2p",
        "message": "chore: update nginx access log format to include request_time",
        "author": "alex.kumar",
        "minutes_ago": 120,
        "files_changed": ["infra/nginx/nginx.conf"],
        "scenario": "none",
    },
    {
        "sha": "q3r4s5t",
        "message": "fix: patch memory leak in background task scheduler — add cleanup on worker exit",
        "author": "sarah.chen",
        "minutes_ago": 300,
        "files_changed": [
            "app/tasks/scheduler.py",
            "app/tasks/worker.py",
        ],
        "scenario": "none",
    },
    {
        "sha": "u6v7w8x",
        "message": "feat: implement rate limiting on public API endpoints (100 req/min per IP)",
        "author": "james.wilson",
        "minutes_ago": 480,
        "files_changed": [
            "app/middleware/rate_limiter.py",
            "config/limits.py",
        ],
        "scenario": "none",
    },
    {
        "sha": "y9z0a1b",
        "message": "docs: update API documentation for v2.4 release",
        "author": "priya.patel",
        "minutes_ago": 600,
        "files_changed": [
            "docs/api-reference.md",
            "docs/changelog.md",
        ],
        "scenario": "none",
    },
]


def get_recent_commits(limit: int = 5) -> str:
    """
    Get the most recent Git commits to check for suspicious deployments.

    Args:
        limit: Number of commits to return (default: 5)

    Returns:
        Formatted string of recent commits with authors, files, and timestamps.
    """
    logger.info(f"📋 Fetching last {limit} commits")

    now = datetime.utcnow()
    commits = _COMMIT_TEMPLATES[:limit]

    if not commits:
        return "No recent commits found."

    formatted = f"Last {len(commits)} commits:\n\n"
    for c in commits:
        date = (now - timedelta(minutes=c["minutes_ago"])).isoformat() + "Z"
        files = ", ".join(c["files_changed"])
        formatted += (
            f"• [{c['sha']}] {c['message']}\n"
            f"  Author: {c['author']} | Date: {date}\n"
            f"  Files changed: {files}\n\n"
        )

    return formatted
