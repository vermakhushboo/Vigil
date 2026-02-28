"""Vigil — GitHub commits tool (seeded for hackathon demo).

Returns realistic hardcoded commits that correlate with each
chaos scenario. In production, this would call the GitHub API.
"""
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("vigil.tools.github_finder")

# ─── Seeded commit history (realistic commits for demo) ───
# These are designed to correlate with our chaos scenarios
# so the agent can find a "suspicious" recent commit.
SEEDED_COMMITS = [
    {
        "sha": "a1b2c3d",
        "message": "fix: update error handler middleware to catch unhandled rejections",
        "author": "sarah.chen",
        "date": (datetime.utcnow() - timedelta(minutes=12)).isoformat() + "Z",
        "files_changed": ["app/middleware/error_handler.py", "app/routes/api.py"],
    },
    {
        "sha": "e4f5g6h",
        "message": "refactor: optimize DB connection pool config and timeout settings",
        "author": "james.wilson",
        "date": (datetime.utcnow() - timedelta(minutes=25)).isoformat() + "Z",
        "files_changed": ["config/database.py", "docker-compose.yml"],
    },
    {
        "sha": "i7j8k9l",
        "message": "feat: add request validation layer with schema enforcement",
        "author": "priya.patel",
        "date": (datetime.utcnow() - timedelta(minutes=45)).isoformat() + "Z",
        "files_changed": ["app/validation/schemas.py", "app/middleware/validator.py"],
    },
    {
        "sha": "m0n1o2p",
        "message": "chore: update nginx config and adjust proxy timeout values",
        "author": "alex.kumar",
        "date": (datetime.utcnow() - timedelta(hours=2)).isoformat() + "Z",
        "files_changed": ["infra/nginx/nginx.conf"],
    },
    {
        "sha": "q3r4s5t",
        "message": "fix: patch memory leak in background task scheduler",
        "author": "sarah.chen",
        "date": (datetime.utcnow() - timedelta(hours=5)).isoformat() + "Z",
        "files_changed": ["app/tasks/scheduler.py", "app/tasks/worker.py"],
    },
    {
        "sha": "u6v7w8x",
        "message": "feat: implement rate limiting on public API endpoints",
        "author": "james.wilson",
        "date": (datetime.utcnow() - timedelta(hours=8)).isoformat() + "Z",
        "files_changed": ["app/middleware/rate_limiter.py", "config/limits.py"],
    },
]


def get_recent_commits(limit: int = 5) -> str:
    """
    Get the most recent Git commits to check for suspicious deployments.

    Args:
        limit: Number of commits to return (default: 5)

    Returns:
        Formatted string of recent commits.
    """
    logger.info(f"📋 Fetching last {limit} commits")

    commits = SEEDED_COMMITS[:limit]

    if not commits:
        return "No recent commits found."

    formatted = f"Last {len(commits)} commits:\n\n"
    for c in commits:
        files = ", ".join(c["files_changed"])
        formatted += (
            f"• [{c['sha']}] {c['message']}\n"
            f"  Author: {c['author']} | Date: {c['date']}\n"
            f"  Files: {files}\n\n"
        )

    return formatted
