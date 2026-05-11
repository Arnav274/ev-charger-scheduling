# EV Charging Reservation System (Westminster + Camden)

Three-tier project for the CMP final-year portfolio:
- **Backend**: FastAPI + SQLAlchemy + Alembic
- **Database**: PostgreSQL + PostGIS
- **Frontend**: React + Leaflet (OpenStreetMap tiles)

## What is implemented

- Dockerized stack via `docker-compose.yml`
- PostGIS schema with tables: `users`, `vehicles`, `stations`, `chargers`, `reservations`
- Spatial endpoint using `ST_DWithin`:
  - `GET /stations/nearby?lat=&lon=&radius_km=`
- JWT-backed accounts (`POST /auth/register`, `POST /auth/login`) with bcrypt password hashes (`users.password_hash`).
- Reservation API with overlap blocking (requires `Authorization: Bearer <jwt>`):
  - `POST /reservations` (returns `409` on overlap via exclusion constraint)
- Strategy-based recommendation endpoint:
  - `POST /recommendations` with `nearest`, `cost_optimized`, `queue_aware`
- Erlang-C queueing module:
  - Probability of delay and expected waiting time
- OpenChargeMap ingestion script for Westminster+Camden:
  - cached offline sample included
- `GET /stats/experiment-summary` serialises frozen `experiments/outputs/summary_ci.csv` for the React **Stats** tab.
- Experiment runner + analysis scripts:
  - repeated trials, sensitivity variants, bootstrap CIs, ANOVA, boxplot, Pareto-style plot
- Pytest suite for queueing math, API health, and reservation overlap integration
  - includes endpoint-level API behavior coverage

## Folder structure

- `backend/` FastAPI app, migrations, scripts, tests, experiments
- `frontend/` React Leaflet UI
- `docker-compose.yml` orchestrates db/backend/frontend

## Local run

### 0) Optional: set local API key env var (recommended for live station data)

Copy `.env.example` to `.env` and fill `OPENCHARGEMAP_API_KEY`.

```bash
cp .env.example .env
```

Do **not** commit `.env`.

### 1) Start services

```bash
docker compose up --build
```

### 2) Run database migration

```bash
docker compose exec backend alembic upgrade head
```

### 3) Seed demo data

```bash
docker compose exec backend python -m scripts.seed_demo
docker compose exec backend python -m scripts.ingest_openchargemap
```

After pulling new npm dependencies:

```bash
docker compose exec frontend npm install
```

Use `--live` to fetch real OpenChargeMap data:

```bash
docker compose exec backend python -m scripts.ingest_openchargemap --live
```

Use a custom area for live ingestion (examples):

```bash
# Westminster/Camden-like central London fetch
docker compose exec backend python -m scripts.ingest_openchargemap --live --latitude 51.52 --longitude -0.13 --distance-km 10 --max-results 300

# Norwich fetch
docker compose exec backend python -m scripts.ingest_openchargemap --live --latitude 52.6309 --longitude 1.2974 --distance-km 15 --max-results 300
```

If live fetch returns 403, verify `OPENCHARGEMAP_API_KEY` is set in your shell / `.env`.

`scripts.seed_demo` resets `demo.user@example.com` to a bcrypt hash (`DEMO_PASSWORD` env overrides default `DemoPass123!`) at fixed UUID `a0000001-0000-4000-8000-000000000001`; it deletes prior demo-linked reservations first.

### 4) Open apps

- Frontend: <http://localhost:5173>
- Backend docs: <http://localhost:8000/docs>

## API quick examples

Authenticate (returns JWT):

```bash
curl -X POST "http://localhost:8000/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email":"researcher@uea.invalid","password":"LongPassword1"}'
```

```bash
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=demo.user@example.com&password=DemoPass123!"
```

Reserve a charger (paste token):

```bash
curl -X POST "http://localhost:8000/reservations" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_HERE" \
  -d '{"charger_id":"CHARGER_UUID","start_time":"2026-05-10T10:00:00Z","end_time":"2026-05-10T11:30:00Z"}'
```

```bash
curl "http://localhost:8000/stations/nearby?lat=51.5074&lon=-0.1278&radius_km=5"
```

```bash
curl -X POST "http://localhost:8000/recommendations" \
  -H "Content-Type: application/json" \
  -d "{\"origin_lat\":51.5074,\"origin_lon\":-0.1278,\"algorithm\":\"queue_aware\",\"radius_km\":5,\"top_k\":5}"
```

## Testing

Run unit tests in backend container:

```bash
docker compose exec backend pytest -q
```

The reservation overlap test is integration-level and expects a running migrated Postgres instance.

Run frontend tests:

```bash
cd frontend
npm test
```

Coverage artifact command:

```bash
docker compose exec backend pytest --cov=. --cov-report=xml --cov-report=term-missing
```

## Reproducible experiments

```bash
docker compose exec backend python -m experiments.run_experiments
docker compose exec backend python -m experiments.analyse_results
```

One-command freeze cycle (recommended before writing final report claims):

```bash
python tools/freeze_cycle.py
```

`freeze_run_metadata.json` records branch, short SHA, and worktree cleanliness when available. If no commits exist yet, commit fields are set to `unknown`.

Generated artifacts:
- `backend/experiments/outputs/experiment_results.csv`
- `backend/experiments/outputs/experiment_summary_metrics.csv`
- `backend/experiments/outputs/summary_ci.csv`
- `backend/experiments/outputs/anova.txt`
- `backend/experiments/outputs/posthoc_wait.csv`
- `backend/experiments/outputs/analysis_notes.md`
- `backend/experiments/outputs/sensitivity_summary.csv`
- `backend/experiments/outputs/freeze_run_metadata.json`
- `backend/experiments/outputs/boxplot_wait_time.png`
- `backend/experiments/outputs/pareto_distance_wait.png`

Submission and report-traceability guides:
- `docs/evidence_for_dissertation/EVALUATION_ARTIFACTS.md` — verbatim stats / figure checklist
- `docs/evidence_for_dissertation/STACK_CHOICE_AND_PREPARATION.md` — preparation narrative
- `docs/threat_model_and_ethics_scope.md` — LO5 / security scope
- `docs/privacy_and_ethics_ui_copy.md` — mirrors UI privacy tab
- `docs/submission_pack.md`
- `docs/report_alignment_checklist.md`
- `docs/VERIFICATION_RUN.md` — automated test / freeze log (refresh after major changes)
- `docs/E2E_USER_JOURNEYS.md` — demo and screenshot walkthrough
- `docs/ONEDRIVE_PACKAGING_CHECKLIST.md` — assemble OneDrive submission folder

Presentation rehearsal pack (`presentation/`):
- `DEMO_SCRIPT.md`, `OFFLINE_FALLBACK.md`, `SCREENSHOT_CAPTURE_CHECKLIST.md`, `captures/`

## Notes for portfolio evidence

- **City map requirement**: satisfied by PostGIS + nearby station endpoint + map UI.
- **Scheduling algorithms requirement**: three swappable algorithms implemented.
- **Algorithm comparison requirement**: experiment runner + ANOVA + CIs + plots.
- **Reservation platform requirement**: full station browse + charger reservation workflow with conflict rejection.
