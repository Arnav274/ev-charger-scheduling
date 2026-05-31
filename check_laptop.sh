#!/bin/bash
# Run this on the laptop after git reset --hard origin/main
# It checks every critical piece of the system and prints PASS or FAIL

PASS=0
FAIL=0

ok()  { echo "✅ $1"; ((PASS++)); }
bad() { echo "❌ $1"; ((FAIL++)); }

echo "=== Docker containers ==="
docker compose ps --format "{{.Name}} {{.Status}}" 2>/dev/null | while read name status; do
  echo "  $name: $status"
done

echo ""
echo "=== Critical files in repo ==="
files=(
  "backend/experiments/outputs/summary_ci.csv"
  "backend/experiments/outputs/algorithm_comparison_bar.png"
  "backend/experiments/outputs/boxplot_wait_time.png"
  "backend/experiments/outputs/anova.txt"
  "backend/experiments/outputs/posthoc_wait.csv"
  "frontend/src/App.jsx"
  "frontend/src/EthicsPanel.jsx"
  "frontend/src/StatsDashboard.jsx"
  "frontend/src/styles.css"
)
for f in "${files[@]}"; do
  [ -f "$f" ] && ok "$f" || bad "$f MISSING"
done

echo ""
echo "=== Backend API ==="
health=$(curl -s http://localhost:8000/health 2>/dev/null)
echo "$health" | grep -q "ok" && ok "Health endpoint" || bad "Health endpoint — backend not responding"

count=$(curl -s "http://localhost:8000/stations/nearby?lat=51.5074&lon=-0.1278&radius_km=5" 2>/dev/null | python3 -c "import json,sys;d=json.load(sys.stdin);print(len(d))" 2>/dev/null)
[ "$count" -ge 50 ] 2>/dev/null && ok "Stations loaded: $count" || bad "Stations: got '$count' (need 50+)"

login=$(curl -s -X POST "http://localhost:8000/auth/login" -H "Content-Type: application/x-www-form-urlencoded" -d "username=demo.user@example.com&password=DemoPass123!" 2>/dev/null)
echo "$login" | grep -q "access_token" && ok "Demo login works" || bad "Demo login FAILED"

stats=$(curl -s "http://localhost:8000/stats/experiment-summary" 2>/dev/null | python3 -c "import json,sys;d=json.load(sys.stdin);print(len(d['rows']))" 2>/dev/null)
[ "$stats" -eq 162 ] 2>/dev/null && ok "Stats endpoint: $stats rows" || bad "Stats endpoint: got '$stats' (need 162)"

osrm=$(curl -s "http://localhost:5000/route/v1/driving/-0.1278,51.5074;-0.1195,51.5033" 2>/dev/null)
echo "$osrm" | grep -q "routes" && ok "OSRM routing works" || bad "OSRM not responding"

echo ""
echo "=== Frontend ==="
frontend=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5173 2>/dev/null)
[ "$frontend" = "200" ] && ok "Frontend serving (HTTP 200)" || bad "Frontend not responding (got $frontend)"

echo ""
echo "=== Test suite ==="
docker compose exec backend pytest -q 2>/dev/null | tail -1

echo ""
echo "=== RESULT: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] && echo "Everything looks good." || echo "Fix the items marked ❌ above."
