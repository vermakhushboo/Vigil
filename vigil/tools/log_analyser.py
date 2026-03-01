"""Vigil — Elasticsearch log search tool.

Queries the app-logs-* index in Elasticsearch for error logs
matching a search query within a time range.
"""
import logging
from datetime import datetime, timedelta

from elasticsearch import Elasticsearch

from vigil.config import settings

logger = logging.getLogger("vigil.tools.log_analyser")


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

    Args:
        query: Search terms e.g. 'ERROR cpu memory'
        time_range: Time range e.g. '5m', '15m', '1h'

    Returns:
        Formatted string of matching log entries.
    """
    logger.info(f"🔍 Searching logs: query='{query}', time_range={time_range}")

    try:
        es = Elasticsearch(settings.elasticsearch_url)

        if not es.ping():
            return "Elasticsearch is not reachable. Cannot search logs."

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

        if not hits:
            return f"No logs found matching '{query}' in the last {time_range}."

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

    except Exception as e:
        logger.error(f"Elasticsearch search failed: {e}")
        return f"Error searching logs: {e}. Elasticsearch may not be available."
