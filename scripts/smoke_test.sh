#!/bin/bash
# End-to-end check of a running stack (after `docker compose up` and the setup commands in the
# README). Prints PASS or FAIL for each check, then a summary, and exits non-zero on any failure.

cd "$(dirname "$0")/.." || exit 1

API=http://localhost:8000
PY=$(command -v python3 || command -v python)
PASS=0
FAIL=0

# Assign rather than ((n++)): the post-increment form returns status 1 while the counter is 0.
ok() { echo "PASS  $1"; PASS=$((PASS + 1)); }
bad() { echo "FAIL  $1"; FAIL=$((FAIL + 1)); }
check() { if eval "$2" >/dev/null 2>&1; then ok "$1"; else bad "$1"; fi; }
# Read a value out of a JSON response: json '<python expression over d>'
json() { "$PY" -c "import json, sys; d = json.load(sys.stdin); print($1)"; }

echo "== Services"
check "backend health" "curl -sf $API/health | grep -q ok"
check "OSRM routes a real trip" \
  "curl -sf 'http://localhost:5000/route/v1/driving/-0.1278,51.5074;-0.1195,51.5033' | grep -q '\"Ok\"'"
check "frontend serves" "curl -sf http://localhost:5173 | grep -q 'id=\"root\"'"

echo "== Data"
stations=$(curl -sf "$API/stations/nearby?lat=51.5074&lon=-0.1278&radius_km=5" | json 'len(d)')
if [ "${stations:-0}" -ge 50 ] 2>/dev/null; then ok "stations loaded ($stations)"; else bad "stations loaded (got '${stations}', need 50+)"; fi
check "road graph built" "test -f backend/data/road_graph.npz"

echo "== Recommendations"
for algorithm in nearest dijkstra cost_optimized static_queue queue_aware range_aware; do
  count=$(curl -sf -X POST "$API/recommendations" -H 'Content-Type: application/json' \
    -d "{\"origin_lat\": 51.5074, \"origin_lon\": -0.1278, \"algorithm\": \"$algorithm\", \"top_k\": 3}" |
    json 'len(d)')
  if [ "${count:-0}" -eq 3 ] 2>/dev/null; then ok "$algorithm returns 3 stations"; else bad "$algorithm returns 3 stations (got '${count}')"; fi
done

echo "== Accounts and booking"
demo=$(curl -sf -X POST "$API/auth/login" -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'username=demo.user@example.com&password=DemoPass123!' | json 'd["access_token"]')
if [ -n "$demo" ]; then ok "demo login"; else bad "demo login (run scripts.seed_demo)"; fi
# Book with a throwaway account, because the demo user already holds the seeded bookings.
token=$(curl -sf -X POST "$API/auth/register" -H 'Content-Type: application/json' \
  -d "{\"email\": \"smoke-$RANDOM$RANDOM@example.com\", \"password\": \"SmokeTest123\"}" | json 'd["access_token"]')
if [ -n "$token" ]; then ok "registration"; else bad "registration"; fi
station=$(curl -sf "$API/stations/nearby?lat=51.5074&lon=-0.1278&radius_km=1" | json 'd[0]["id"]')
charger=$(curl -sf "$API/stations/$station" | json 'd["chargers"][0]["id"]')
# A random hour far in the future, so repeated runs do not collide with their own bookings.
start=$("$PY" -c "import datetime as t, random; print((t.datetime(2040, 1, 1) + t.timedelta(hours=random.randrange(10**5))).isoformat() + 'Z')")
end=$("$PY" -c "import datetime as t; print((t.datetime.fromisoformat('${start%Z}') + t.timedelta(hours=1)).isoformat() + 'Z')")
book() {
  curl -s -o /dev/null -w '%{http_code}' -X POST "$API/reservations" -H "Authorization: Bearer $token" \
    -H 'Content-Type: application/json' -d "{\"charger_id\": \"$charger\", \"start_time\": \"$start\", \"end_time\": \"$end\"}"
}
[ "$(book)" = "201" ] && ok "booking accepted" || bad "booking accepted"
[ "$(book)" = "409" ] && ok "double booking rejected" || bad "double booking rejected"

echo "== Experiment results"
check "committed results present" \
  "test -f backend/experiments/outputs/summary_ci.csv -a -f backend/experiments/outputs/findings.json"
expected=$(curl -sf "$API/stats/findings" | json 'len(d["study"]["variants"]) * len(d["study"]["scenarios"]) * 6')
rows=$(curl -sf "$API/stats/experiment-summary" | json 'len(d["rows"])')
if [ -n "$rows" ] && [ "$rows" = "$expected" ]; then ok "stats endpoint serves every condition ($rows)"; else bad "stats endpoint rows (got '${rows}', expected '${expected}')"; fi

echo "== Test suites"
check "backend tests" "docker compose exec -T -e REQUIRE_DB=1 backend pytest -q"

echo
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
