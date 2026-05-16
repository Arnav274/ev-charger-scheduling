# Daily dev guide (Windows + Docker + PowerShell)

Use this when you **open the project tomorrow**, **reboot**, or **change code** and need to know what to run.

**Project root** (adjust if yours differs):

`D:\Projects\Uni\dissertation\ev-3.0-`

---

## 1. Every day: start the stack

Open **PowerShell**, go to the repo, start containers:

```powershell
Set-Location "D:\Projects\Uni\dissertation\ev-3.0-"
docker compose up -d
```

**First time after cloning** (or after `docker compose down -v`):

```powershell
Set-Location "D:\Projects\Uni\dissertation\ev-3.0-"
docker compose up --build -d
```

**Check everything is up** (especially OSRM — it must not be `Exited`):

```powershell
docker compose ps
```

- **Frontend:** http://localhost:5173  
- **API docs:** http://localhost:8000/docs  
- **Health:** http://localhost:8000/health  

**If OSRM shows `Exited`:** give Docker/WSL enough RAM (see README / your `.wslconfig`), then:

```powershell
wsl --shutdown
```

Re-open **Docker Desktop**, then `docker compose up -d` again.

---

## 2. First-time DB setup (only when the database is empty)

Skip this block if you already ran it and did **not** wipe volumes (`down -v`).

```powershell
Set-Location "D:\Projects\Uni\dissertation\ev-3.0-"
docker compose exec backend alembic upgrade head
docker compose exec backend python -m scripts.seed_demo
docker compose exec backend python -m scripts.ingest_openchargemap
docker compose exec backend python -m scripts.seed_background_reservations
```

**Live OpenChargeMap** (needs `OPENCHARGEMAP_API_KEY` in `.env` next to `docker-compose.yml`, then recreate backend once):

```powershell
docker compose up -d --force-recreate backend
docker compose exec backend python -m scripts.ingest_openchargemap --live --latitude 51.52 --longitude -0.13 --distance-km 10 --max-results 300
docker compose exec backend python -m scripts.seed_background_reservations
```

**Demo login:** `demo.user@example.com` / `DemoPass123!` (unless `DEMO_PASSWORD` in `.env` overrides).

---

## 3. After you change code

| What you changed | What to do |
|------------------|------------|
| **Python** under `backend/` | Usually **nothing** — uvicorn `--reload` picks it up. If behaviour looks stale: `docker compose restart backend`. |
| **`docker-compose.yml`**, **Dockerfile**, **new pip deps** | `docker compose up --build -d` |
| **`.env`** (API key, secrets) | `docker compose up -d --force-recreate backend` |
| **Frontend** under `frontend/` | Vite reloads in dev; if odd: `docker compose restart frontend` or `docker compose exec frontend npm install` |

---

## 4. Demo hotspot (repeat when the printed time is in the past)

The seed script prints an `arrival_time_target` in the **future**. After a day or two, run:

```powershell
Set-Location "D:\Projects\Uni\dissertation\ev-3.0-"
docker compose exec backend python -m scripts.seed_background_reservations
```

Use the printed JSON payload to compare **`queue_aware`** vs **`static_queue`** in the UI or `POST /recommendations`.

---

## 5. Experiments (optional, for dissertation artefacts)

**Requires OSRM `Up`.** Can take **a long time** with many stations (leave it running; do not paste two commands on one line).

```powershell
Set-Location "D:\Projects\Uni\dissertation\ev-3.0-"
docker compose exec backend python -m experiments.run_experiments
```

When you see `Saved: /app/experiments/outputs/experiment_results.csv` and the prompt returns, run:

```powershell
docker compose exec backend python -m experiments.analyse_results
```

Outputs appear on the **host** at `backend\experiments\outputs\` (same as `/app/experiments/outputs/` in the container).

**Optional metadata freeze** (from repo root, if you use the tool in README):

```powershell
python tools/freeze_cycle.py
```

---

## 6. Quick checks (copy-paste)

```powershell
# Containers
docker compose ps

# API alive
Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing | Select-Object Content

# Backend tests
docker compose exec backend pytest -q
```

---

## 7. Shut down for the day

```powershell
Set-Location "D:\Projects\Uni\dissertation\ev-3.0-"
docker compose stop
```

**Wipe DB + OSRM data volumes** (only if you really want a clean slate):

```powershell
docker compose down -v
```

---

## 8. One-line “I’m back” checklist

1. `docker compose up -d`  
2. `docker compose ps` → **osrm** = **Up**  
3. Open http://localhost:5173  
4. If demo looks empty or times are wrong → `seed_background_reservations` again  

Full narrative setup stays in the root **README.md**.
