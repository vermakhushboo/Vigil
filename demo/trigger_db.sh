#!/bin/bash
# Trigger a PostgreSQL down alert by stopping the Postgres container.
# Usage: bash demo/trigger_db.sh

set -e

echo "🔥 Stopping PostgreSQL container to simulate DB failure ..."
docker compose stop postgres

echo ""
echo "⏳ PostgreSQL is now STOPPED."
echo "   Wait ~30s for the PostgresDown alert to fire."
echo "   Check: http://localhost:9093 (Alertmanager)"
echo "   Check: http://localhost:9090/alerts (Prometheus)"
echo ""
echo "📝 To restore PostgreSQL, run:"
echo "   docker compose start postgres"
