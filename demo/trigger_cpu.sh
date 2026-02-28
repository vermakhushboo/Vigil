#!/bin/bash
# Trigger a CPU spike on the Flask chaos app.
# Usage: bash demo/trigger_cpu.sh

set -e

FLASK_URL="${FLASK_URL:-http://localhost:80}"
DURATION="${1:-30}"

echo "🔥 Triggering CPU spike for ${DURATION}s on $FLASK_URL/chaos/cpu ..."
curl -s "$FLASK_URL/chaos/cpu?duration=$DURATION" | python3 -m json.tool

echo ""
echo "✅ CPU spike triggered!"
echo "⏳ The Flask app is now under CPU load for ${DURATION}s."
echo "   Check: http://localhost:9090/graph (search for process_cpu_seconds)"
