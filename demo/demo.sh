#!/bin/bash
# Run all chaos scenarios sequentially for a demo.
# Usage: bash demo/demo.sh

set -e

echo "╔═══════════════════════════════════════════════╗"
echo "║     🔍 VIGIL — Full Demo Sequence             ║"
echo "╚═══════════════════════════════════════════════╝"
echo ""

# Scenario 1: 5xx Errors
echo "━━━ Scenario 1: HTTP 500 Errors ━━━"
bash demo/trigger_500.sh 10
echo ""
echo "⏳ Waiting 30s for alert to fire..."
sleep 30

# Scenario 2: Database Down
echo ""
echo "━━━ Scenario 2: Database Failure ━━━"
bash demo/trigger_db.sh
echo ""
echo "⏳ Waiting 30s for alert to fire..."
sleep 30

# Restore DB
echo ""
echo "📦 Restoring PostgreSQL..."
docker compose start postgres
sleep 5

# Scenario 3: CPU Spike
echo ""
echo "━━━ Scenario 3: CPU Spike ━━━"
bash demo/trigger_cpu.sh 30
echo ""
echo "⏳ Waiting for CPU spike to complete..."
sleep 35

echo ""
echo "╔═══════════════════════════════════════════════╗"
echo "║     ✅ Demo Complete!                          ║"
echo "╚═══════════════════════════════════════════════╝"
echo ""
echo "Check incidents: curl http://localhost:8000/incidents | python3 -m json.tool"
