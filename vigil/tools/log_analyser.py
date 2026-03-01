"""Vigil — Elasticsearch log search tool.

Queries the app-logs-* index in Elasticsearch for error logs.
Falls back to seeded scenario-specific logs when ES has no data
(e.g., during /test/trigger demos without actual chaos).
"""
import logging
from datetime import datetime, timedelta

from elasticsearch import Elasticsearch

from vigil.config import settings

logger = logging.getLogger("vigil.tools.log_analyser")


# ─── Seeded logs: realistic entries per scenario ───
# These are returned when ES has no data, so the agent always has logs to work with.
# Keys are matched against the search query (case-insensitive substring match).

def _make_logs(base_minutes_ago: int, entries: list[dict]) -> list[dict]:
    """Generate timestamped log entries relative to now."""
    now = datetime.utcnow()
    return [
        {
            "@timestamp": (now - timedelta(minutes=base_minutes_ago - i)).isoformat() + "Z",
            **entry,
        }
        for i, entry in enumerate(entries)
    ]


_SEEDED_LOG_SCENARIOS = {
    # ─── 5xx / HTTP errors ───
    "500": lambda: _make_logs(5, [
        {"level": "ERROR", "service": "flask-app", "message": "HTTP 500 Internal Server Error on POST /api/orders — Traceback: NoneType has no attribute 'get'", "exception": "AttributeError: 'NoneType' object has no attribute 'get' in error_handler.py:42"},
        {"level": "ERROR", "service": "flask-app", "message": "HTTP 500 Internal Server Error on GET /api/users/profile — unhandled exception in middleware", "exception": "TypeError: expected str, got NoneType in middleware/error_handler.py:38"},
        {"level": "ERROR", "service": "flask-app", "message": "HTTP 500 Internal Server Error on POST /api/checkout — request body parsing failed", "exception": "JSONDecodeError: Expecting value at line 1 in error_handler.py:42"},
        {"level": "WARNING", "service": "flask-app", "message": "Error rate threshold breached: 47 errors in last 60 seconds (threshold: 5)"},
        {"level": "ERROR", "service": "flask-app", "message": "HTTP 500 Internal Server Error on GET /api/products — null reference in error handler", "exception": "AttributeError: 'NoneType' object has no attribute 'get' in error_handler.py:42"},
        {"level": "ERROR", "service": "nginx", "message": "upstream returned 500 while reading response from flask-app:5001/api/orders"},
        {"level": "ERROR", "service": "flask-app", "message": "HTTP 500 Internal Server Error on POST /api/payments — middleware crash", "exception": "AttributeError: 'NoneType' object has no attribute 'get' in error_handler.py:42"},
        {"level": "INFO", "service": "flask-app", "message": "Deployment completed: version 2.4.1 (commit a1b2c3d) — 12 minutes ago"},
    ]),
    "5xx": lambda: _make_logs(5, [
        {"level": "ERROR", "service": "flask-app", "message": "HTTP 500 Internal Server Error on POST /api/orders — Traceback: NoneType has no attribute 'get'", "exception": "AttributeError: 'NoneType' object has no attribute 'get' in error_handler.py:42"},
        {"level": "ERROR", "service": "flask-app", "message": "HTTP 502 Bad Gateway — upstream connection refused on flask-app:5001"},
        {"level": "ERROR", "service": "flask-app", "message": "HTTP 500 Internal Server Error on GET /api/users — middleware crash after deploy", "exception": "TypeError: expected str, got NoneType in middleware/error_handler.py:38"},
        {"level": "WARNING", "service": "nginx", "message": "5xx error rate 23/min on upstream flask-app (threshold: 5/min)"},
        {"level": "ERROR", "service": "flask-app", "message": "HTTP 500 Internal Server Error on POST /api/checkout — unhandled exception", "exception": "AttributeError in error_handler.py:42"},
    ]),
    "error": lambda: _make_logs(5, [
        {"level": "ERROR", "service": "flask-app", "message": "HTTP 500 Internal Server Error on POST /api/orders — Traceback: NoneType has no attribute 'get'", "exception": "AttributeError: 'NoneType' object has no attribute 'get' in error_handler.py:42"},
        {"level": "ERROR", "service": "flask-app", "message": "Unhandled exception in request handler — error_handler middleware returning 500 for all routes", "exception": "TypeError: expected str, got NoneType in middleware/error_handler.py:38"},
        {"level": "ERROR", "service": "flask-app", "message": "HTTP 500 on GET /health — even health check is failing through the broken error handler"},
        {"level": "WARNING", "service": "flask-app", "message": "Error rate spike detected: 47 errors/min (baseline: 2/min). Started at deployment 2.4.1 (12 min ago)"},
    ]),

    # ─── Database / PostgreSQL ───
    "database": lambda: _make_logs(4, [
        {"level": "CRITICAL", "service": "flask-app", "message": "FATAL: could not connect to PostgreSQL server at postgres:5432 — Connection refused", "exception": "psycopg2.OperationalError: connection to server at 'postgres' (172.18.0.3), port 5432 failed: Connection refused. Is the server running?"},
        {"level": "ERROR", "service": "flask-app", "message": "Database health check failed: pg_isready returns 'no response' — PostgreSQL container may be down"},
        {"level": "ERROR", "service": "flask-app", "message": "GET /api/orders failed — database connection refused after pool timeout (30s)", "exception": "sqlalchemy.exc.OperationalError: could not connect to server: Connection refused"},
        {"level": "WARNING", "service": "flask-app", "message": "Connection pool exhausted: 0/25 connections available. All connections returning 'server closed the connection unexpectedly'"},
        {"level": "ERROR", "service": "flask-app", "message": "POST /api/checkout failed — cannot execute INSERT: server closed the connection", "exception": "psycopg2.InterfaceError: connection already closed"},
        {"level": "CRITICAL", "service": "postgres-exporter", "message": "pg_up metric = 0 — PostgreSQL is not responding to health checks"},
    ]),
    "postgres": lambda: _make_logs(4, [
        {"level": "CRITICAL", "service": "flask-app", "message": "FATAL: could not connect to PostgreSQL at postgres:5432 — Connection refused", "exception": "psycopg2.OperationalError: Connection refused. Is the server running on host 'postgres' and accepting TCP/IP connections on port 5432?"},
        {"level": "ERROR", "service": "flask-app", "message": "Database connection pool drained: 0 available, 25/25 connections dead. Last error: server closed the connection unexpectedly"},
        {"level": "ERROR", "service": "flask-app", "message": "All database-dependent endpoints returning HTTP 500 — cascade failure from PostgreSQL down"},
        {"level": "WARNING", "service": "postgres-exporter", "message": "pg_up=0 for 120 seconds — PostgreSQL container is not running"},
    ]),
    "connection": lambda: _make_logs(4, [
        {"level": "CRITICAL", "service": "flask-app", "message": "FATAL: could not connect to PostgreSQL server — Connection refused", "exception": "psycopg2.OperationalError: Connection refused"},
        {"level": "ERROR", "service": "flask-app", "message": "Connection pool health check failed: all 25 connections are dead"},
        {"level": "ERROR", "service": "flask-app", "message": "Request to /api/users timed out waiting for database connection (30s timeout exceeded)"},
    ]),

    # ─── CPU / Performance ───
    "cpu": lambda: _make_logs(6, [
        {"level": "WARNING", "service": "flask-app", "message": "CPU utilization at 94% sustained for 180 seconds — container cpu_quota nearly exhausted"},
        {"level": "WARNING", "service": "flask-app", "message": "Request latency p95 = 8.3s (baseline: 120ms). All endpoints affected. Correlates with CPU spike."},
        {"level": "ERROR", "service": "flask-app", "message": "GET /api/reports/generate timed out after 30s — handler consumed 28.7s of CPU time in JSON serialization loop", "exception": "TimeoutError: request processing exceeded 30s limit"},
        {"level": "WARNING", "service": "flask-app", "message": "Health check response time: 4200ms (threshold: 500ms). Container at risk of being killed by orchestrator."},
        {"level": "ERROR", "service": "flask-app", "message": "Worker process PID 847 using 97.2% CPU — stuck in data_processor.transform_batch() with 50MB payload"},
        {"level": "WARNING", "service": "nginx", "message": "Upstream flask-app:5001 response time 12.4s — 4 requests queued behind slow handler"},
    ]),
    "latency": lambda: _make_logs(6, [
        {"level": "WARNING", "service": "flask-app", "message": "Request latency p95 = 8.3s (baseline: 120ms). Spike correlates with CPU at 94%."},
        {"level": "ERROR", "service": "flask-app", "message": "GET /api/reports/generate timed out — 28.7s CPU time in transform_batch()", "exception": "TimeoutError: request exceeded 30s limit"},
        {"level": "WARNING", "service": "flask-app", "message": "5 requests queued — all waiting for CPU-bound handler to complete"},
    ]),
    "spike": lambda: _make_logs(6, [
        {"level": "WARNING", "service": "flask-app", "message": "CPU utilization at 94% for 180s — triggered by data_processor.transform_batch()"},
        {"level": "ERROR", "service": "flask-app", "message": "Request timeout on /api/reports/generate — CPU-bound for 28.7s", "exception": "TimeoutError"},
        {"level": "WARNING", "service": "flask-app", "message": "Health check degraded: 4200ms response time (threshold: 500ms)"},
    ]),
}


def _match_seeded_logs(query: str) -> str | None:
    """Try to match query against seeded log scenarios."""
    query_lower = query.lower()

    # Try exact keyword matches first, then partial
    for keyword, log_fn in _SEEDED_LOG_SCENARIOS.items():
        if keyword in query_lower:
            logs = log_fn()
            formatted = f"Found {len(logs)} log entries matching '{query}':\n\n"
            for log in logs:
                entry = f"[{log['@timestamp']}] [{log['level']}] [{log['service']}] {log['message']}"
                if log.get("exception"):
                    entry += f"\n  Exception: {log['exception']}"
                formatted += entry + "\n"
            return formatted

    return None


def _parse_time_range(time_range: str) -> datetime:
    """Convert a time range string like '5m', '15m', '1h' to a datetime."""
    try:
        unit = time_range[-1]
        value = int(time_range[:-1])
    except (ValueError, IndexError):
        logger.warning(f"Invalid time_range '{time_range}', defaulting to 10m")
        return datetime.utcnow() - timedelta(minutes=10)

    if unit == "m":
        return datetime.utcnow() - timedelta(minutes=value)
    elif unit == "h":
        return datetime.utcnow() - timedelta(hours=value)
    elif unit == "d":
        return datetime.utcnow() - timedelta(days=value)
    else:
        return datetime.utcnow() - timedelta(minutes=10)


def search_logs(query: str, time_range: str = "10m") -> str:
    """
    Search Elasticsearch for recent logs matching the query.

    Falls back to seeded scenario-specific logs when ES has no data.

    Args:
        query: Search terms e.g. 'ERROR 500 exception'
        time_range: Time range e.g. '5m', '15m', '1h'

    Returns:
        Formatted string of matching log entries.
    """
    logger.info(f"🔍 Searching logs: query='{query}', time_range={time_range}")

    try:
        es = Elasticsearch(settings.elasticsearch_url)

        if not es.ping():
            logger.warning("Elasticsearch not reachable, trying seeded logs")
            return _match_seeded_logs(query) or "Elasticsearch is not reachable. Cannot search logs."

        since = _parse_time_range(time_range)

        result = es.search(
            index="app-logs-*",
            query={
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": ["message", "level", "service", "exception"],
                                "type": "best_fields",
                                "fuzziness": "AUTO",
                            }
                        }
                    ],
                    "filter": [
                        {
                            "range": {
                                "@timestamp": {
                                    "gte": since.isoformat() + "Z",
                                    "lte": "now",
                                }
                            }
                        }
                    ],
                }
            },
            sort=[{"@timestamp": {"order": "desc"}}],
            size=20,
        )
        hits = result.get("hits", {}).get("hits", [])

        if hits:
            formatted_logs = []
            for hit in hits:
                src = hit.get("_source", {})
                timestamp = src.get("@timestamp", src.get("timestamp", "unknown"))
                level = src.get("level", "INFO")
                message = src.get("message", "")
                service = src.get("service", "unknown")
                exception = src.get("exception", "")

                entry = f"[{timestamp}] [{level}] [{service}] {message}"
                if exception:
                    entry += f"\n  Exception: {exception}"
                formatted_logs.append(entry)

            summary = f"Found {len(hits)} log entries matching '{query}' in the last {time_range}:\n\n"
            summary += "\n".join(formatted_logs)
            return summary

        # ES returned no hits — fall back to seeded logs
        logger.info("No real logs in ES, falling back to seeded logs")
        seeded = _match_seeded_logs(query)
        if seeded:
            return seeded

        return f"No logs found matching '{query}' in the last {time_range}."

    except Exception as e:
        logger.error(f"Elasticsearch search failed: {e}")
        # Try seeded logs as last resort
        seeded = _match_seeded_logs(query)
        if seeded:
            return seeded
        return f"Error searching logs: {e}. Elasticsearch may not be available."
