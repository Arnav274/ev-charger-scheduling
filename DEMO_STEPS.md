## Demo steps (reproducible)

### 1) Start stack

```bash
docker compose up --build
docker compose exec backend alembic upgrade head
```

### 2) Ingest real stations (50+)

If you have an OpenChargeMap key:

```bash
docker compose exec backend python -m scripts.ingest_openchargemap --live --latitude 51.52 --longitude -0.13 --distance-km 10 --max-results 300
```

Otherwise, you can still run with the cached sample (not ideal for evaluation).

### 3) Seed demo user + deterministic hotspot reservations

```bash
docker compose exec backend python -m scripts.seed_demo
docker compose exec backend python -m scripts.seed_background_reservations
```

The seeding script prints a suggested recommendation payload with an `arrival_time_target` and `arrival_window_minutes`.

### 4) Show predictive divergence (API)

- Call `/recommendations` twice with identical inputs, changing only `algorithm`:
  - `static_queue` (baseline)
  - `queue_aware` (predictive)

Key expected result:
- `queue_aware` returns **higher** `predicted_wait_min` and `probability_of_delay` at hotspot stations (because it looks ahead at overlapping reservations).

### 5) Show hotspot reduction (UI)

- Open frontend at `http://localhost:5173`.
- Click **Queue-aware** recommendations.
- Toggle **Show hotspots (predictive delay)**.
- Re-run with **Static queue (baseline)** and compare intensity changes.

