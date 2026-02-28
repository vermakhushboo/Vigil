#!/bin/bash
# Trigger 5xx errors on the Flask chaos app to fire the High5xxRate alert.
# Usage: bash demo/trigger_500.sh

set -e

FLASK_URL="${FLASK_URL:-http://localhost:80}"
COUNT="${1:-10}"

echo "🔥 Triggering $COUNT HTTP 500 errors on $FLASK_URL/chaos/500 ..."
echo ""

for i in $(seq 1 "$COUNT"); do
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$FLASK_URL/chaos/500")
    echo "  [$i/$COUNT] GET /chaos/500 → HTTP $STATUS"
    sleep 0.5
done

echo ""
echo "✅ Done! $COUNT 500 errors sent."
echo "⏳ Wait ~30-60s for the Prometheus alert rule to fire."
echo "   Check: http://localhost:9093 (Alertmanager)"
echo "   Check: http://localhost:9090/alerts (Prometheus)"
