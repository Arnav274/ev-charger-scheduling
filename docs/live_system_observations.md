# Live System Observations - localhost:8000

# Date: 17 May 2026

# Environment: Docker, FastAPI backend, PostgreSQL/PostGIS, OSRM routing



## GET /stations/nearby

Request: lat=51.5074, lon=-0.1278, radius_km=1

Result: 36 stations returned

All in Westminster borough

Sorted by distance_m ascending

Closest: BMM-CP-000504 at 6.18m

Furthest in result: Almacantar at 998.34m

All stations have: id (UUID), name, borough, lat, lon,

price_pence_per_kwh (all 55.0), distance_m



## POST /recommendations - algorithm: nearest

Request: origin_lat=51.5074, origin_lon=-0.1278, radius_km=1

Top 5 results in order:

1\. BMM-CP-000504 | score=0.1373 | distance=0.14km | travel=0.42min | wait=40.00min | P(delay)=0.50 | occupancy=0

2\. Masterpark Trafalgar Square Car Park | score=0.2289 | distance=0.23km | travel=0.79min | wait=40.00min | P(delay)=0.50 | occupancy=0

3\. Coutts Bank | score=0.2965 | distance=0.30km | travel=0.80min | wait=40.00min | P(delay)=0.50 | occupancy=0

4\. Westminster-Whitehall Place | score=0.4976 | distance=0.50km | travel=1.37min | wait=2.67min | P(delay)=0.10 | occupancy=0

5\. Q-Park Leicester Square Car Park | score=0.5037 | distance=0.50km | travel=1.48min | wait=0.02min | P(delay)=0.002 | occupancy=0



## POST /recommendations - algorithm: queue_aware

Request: origin_lat=51.5074, origin_lon=-0.1278, radius_km=1

Top 5 results in order:

1\. Q-Park Leicester Square Car Park | score=0.0354 | distance=0.50km | travel=1.48min | wait=0.02min | P(delay)=0.002 | occupancy=0

2\. Stirling Square | score=0.0459 | distance=0.66km | travel=1.85min | wait=0.02min | P(delay)=0.002 | occupancy=0

3\. Q-Park Trafalgar Car Park | score=0.0476 | distance=0.69km | travel=1.98min | wait=0.0000003min | P(delay)=0.00000006 | occupancy=0

4\. Q-Park Chinatown | score=0.0608 | distance=0.88km | travel=2.48min | wait=0.0000000007min | P(delay)=0.0000000002 | occupancy=0

5\. Westminster-Whitehall Place | score=0.0912 | distance=0.50km | travel=1.37min | wait=2.67min | P(delay)=0.10 | occupancy=0



## POST /recommendations - unknown algorithm

Request: algorithm="algorithm"

Response: 400 Bad Request - "Unknown algorithm 'algorithm'"



## Observations (factual only, no interpretation)

\- nearest and queue_aware return different station orderings

\- BMM-CP-000504 is rank 1 for nearest, absent from queue_aware top 5

\- Q-Park Leicester Square is rank 5 for nearest, rank 1 for queue_aware

\- Both algorithms return 200 status with valid JSON

\- OSRM travel times present in all results (not haversine fallback)

\- All predicted_wait_min values are non-negative

\- All probability_of_delay values are between 0 and 1

\- Invalid algorithm name returns 400 not 500

## POST /recommendations - all 6 algorithms (top result only)

Origin: 51.5074, -0.1278, radius_km=1



nearest:      BMM-CP-000504        | dist=0.14km | wait=40.00min | P(delay)=0.50 | score=0.1373

dijkstra:     BMM-CP-000504        | dist=0.14km | wait=40.00min | P(delay)=0.50 | score=0.0062

static_queue: Q-Park Leicester Sq  | dist=0.50km | wait=0.02min  | P(delay)=0.002 | score=0.4111

queue_aware:  Q-Park Leicester Sq  | dist=0.50km | wait=0.02min  | P(delay)=0.002 | score=0.0354

cost_optimized: [paste your result]

range_aware:  BMM-CP-000504        | dist=0.14km | wait=40.00min | P(delay)=0.50 | score=0.1373



## POST /stations/{id}/suggest-slot

Station: Q-Park Leicester Square (6fe1a1aa)

Request: desired_arrival=2026-05-17T11:48:36, duration_minutes=1, 

&#x20;        charger_id=3fa85f64 (fake docs UUID)

Response: [] (empty - correct, charger_id did not exist)

Note: empty list returned correctly when charger not found



## Stats tab

Status: "Could not load experiment summary: Failed to fetch"

Cause: Docker containers not running when browser was opened

Resolution: refresh after Docker up resolves it

