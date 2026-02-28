"""Flask chaos application - simulates a production service with failure modes."""
import os
import time
import json
import logging
import threading
from datetime import datetime

from flask import Flask, jsonify, request, Response
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
import psycopg2

app = Flask(__name__)

# ─── Logging (structured JSON to stdout for Logstash) ───
class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "message": record.getMessage(),
            "service": "flask-app",
            "logger": record.name,
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)

handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
app.logger.handlers = [handler]
app.logger.setLevel(logging.INFO)
logging.getLogger("werkzeug").setLevel(logging.WARNING)

# ─── Prometheus Metrics ───
REQUEST_COUNT = Counter(
    "flask_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"]
)
REQUEST_LATENCY = Histogram(
    "flask_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"]
)
ERROR_COUNT = Counter(
    "flask_http_errors_total",
    "Total HTTP 500 errors",
    ["endpoint"]
)
APP_UP = Gauge("flask_app_up", "Whether the Flask app is up")
APP_UP.set(1)

# ─── Database Config ───
DB_HOST = os.environ.get("POSTGRES_HOST", "postgres")
DB_PORT = os.environ.get("POSTGRES_PORT", "5432")
DB_NAME = os.environ.get("POSTGRES_DB", "vigil")
DB_USER = os.environ.get("POSTGRES_USER", "vigil")
DB_PASS = os.environ.get("POSTGRES_PASSWORD", "vigil_pass")


def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT,
        dbname=DB_NAME, user=DB_USER, password=DB_PASS
    )


# ─── Middleware: track metrics ───
@app.before_request
def before_request():
    request._start_time = time.time()

@app.after_request
def after_request(response):
    # Skip tracking the /metrics endpoint to avoid self-referential noise
    if request.path == "/metrics":
        return response

    latency = time.time() - getattr(request, "_start_time", time.time())
    endpoint = request.path
    REQUEST_COUNT.labels(request.method, endpoint, response.status_code).inc()
    REQUEST_LATENCY.labels(request.method, endpoint).observe(latency)
    if response.status_code >= 500:
        ERROR_COUNT.labels(endpoint).inc()

    app.logger.info(
        f"{request.method} {endpoint} → {response.status_code} ({latency:.3f}s)"
    )
    return response


# ─── Healthy Endpoints ───

@app.route("/")
def index():
    return jsonify({"status": "ok", "service": "flask-app", "timestamp": datetime.utcnow().isoformat()})

@app.route("/health")
def health():
    return jsonify({"status": "healthy"})


# ─── Chaos Endpoints ───

@app.route("/chaos/500")
def chaos_500():
    """Simulate an internal server error."""
    app.logger.error("CHAOS: Internal server error triggered via /chaos/500")
    return jsonify({"error": "Internal Server Error", "chaos": True}), 500

@app.route("/chaos/cpu")
def chaos_cpu():
    """Simulate a CPU spike by running a CPU-intensive loop."""
    duration = int(request.args.get("duration", 30))
    app.logger.warning(f"CHAOS: CPU spike triggered for {duration}s via /chaos/cpu")

    def cpu_burn():
        end_time = time.time() + duration
        while time.time() < end_time:
            _ = sum(i * i for i in range(10000))

    thread = threading.Thread(target=cpu_burn, daemon=True)
    thread.start()
    return jsonify({"status": "cpu_spike_started", "duration_seconds": duration})

@app.route("/chaos/slow-query")
def chaos_slow_query():
    """Simulate a slow database query using pg_sleep."""
    sleep_seconds = int(request.args.get("duration", 10))
    app.logger.warning(f"CHAOS: Slow query triggered ({sleep_seconds}s) via /chaos/slow-query")
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT pg_sleep(%s)", (sleep_seconds,))
        cur.close()
        return jsonify({"status": "slow_query_complete", "duration_seconds": sleep_seconds})
    except Exception as e:
        app.logger.error(f"CHAOS: Database error during slow query: {e}")
        return jsonify({"error": str(e), "chaos": True}), 500
    finally:
        if conn:
            conn.close()

@app.route("/chaos/db-error")
def chaos_db_error():
    """Try to connect to DB — will fail if Postgres is stopped."""
    app.logger.warning("CHAOS: Database connection attempt via /chaos/db-error")
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        return jsonify({"status": "db_connected"})
    except Exception as e:
        app.logger.error(f"CHAOS: Database connection failed: {e}")
        return jsonify({"error": f"Database connection failed: {e}", "chaos": True}), 500
    finally:
        if conn:
            conn.close()


# ─── Prometheus Metrics Endpoint ───

@app.route("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.logger.info(f"Flask chaos app starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
