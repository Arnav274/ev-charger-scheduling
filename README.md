# EV charging reservation (dissertation project)

Find chargers on a map, pick a scheduling algorithm, book a slot. London station data. Needs Docker.

## Run it

From the project folder:

```bash
docker compose up --build
```

First time only (wait until containers are up; OSRM download can take a few minutes):

```bash
docker compose exec backend alembic upgrade head
docker compose exec backend python -m scripts.seed_demo
docker compose exec backend python -m scripts.ingest_openchargemap
```

Optional — more booked slots so `queue_aware` looks different from `static_queue`:

```bash
docker compose exec backend python -m scripts.seed_background_reservations
```

Open:

- App: http://localhost:5173
- API docs: http://localhost:8000/docs

Demo login: `demo.user@example.com` / `DemoPass123!`

## Algorithms

In the app dropdown or in `POST /recommendations` as `"algorithm"`:

`nearest`, `dijkstra`, `static_queue`, `queue_aware`, `cost_optimized`, `range_aware`

Code: `backend/app/algorithms.py`

## Tests

```bash
docker compose exec backend pytest -q
```

## Experiments (already run for the report)

Results are in `backend/experiments/outputs/`.

To run again:

```bash
docker compose exec backend python -m experiments.run_experiments
docker compose exec backend python -m experiments.analyse_results
```

## Folders

- `backend/` — API, database, algorithms, experiments
- `frontend/` — map UI
- `docs/` — report notes (not needed to run the app)

## Live station data (optional)

Copy `.env.example` to `.env`, add `OPENCHARGEMAP_API_KEY`, then:

```bash
docker compose exec backend python -m scripts.ingest_openchargemap --live
```

Default ingest uses a cached sample — no key needed.
