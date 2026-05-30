# EV Charging Reservation System

A full-stack web application that lets electric vehicle drivers find, compare, and book charging stations across London. Built as a university final-year project.

The system uses real London charging station data and implements six different scheduling algorithms to recommend the best station based on distance, predicted wait time, price, or battery range.

---

## What you need before starting

1. **Docker Desktop** — download and install from https://www.docker.com/products/docker-desktop/
   - Make sure Docker Desktop is **running** (you should see the whale icon in your taskbar) before proceeding
   - Windows users: Docker Desktop requires WSL 2 to be enabled — the installer will prompt you if needed

2. **Git** — to clone the repository (you probably already have this)

3. ~**500 MB free disk space** for the London map data

---

## First-time setup (takes ~5–10 minutes)

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/REPO_NAME.git
cd REPO_NAME
```

### 2. Add your API key

Copy the example env file and add your OpenChargeMap API key (free at https://openchargemap.org/site/develop/api):

```bash
cp .env.example .env
```

Open `.env` and fill in your key:
```
OPENCHARGEMAP_API_KEY=your_key_here
```

### 3. Start all services

```bash
docker compose up --build
```

This starts four services: the database, the routing engine (OSRM), the backend API, and the frontend. **The first run downloads and processes the London street map — this takes 5–10 minutes.** You'll see a lot of log output; that's normal.

Wait until you see something like:
```
backend-1  | INFO:     Application startup complete.
frontend-1 | VITE ready in ...ms
```

### 4. Set up the database (first time only)

Open a **second terminal** in the same folder and run these four commands one at a time:

```bash
docker compose exec backend alembic upgrade head
```
*(creates the database tables)*

```bash
docker compose exec backend python -m scripts.seed_demo
```
*(adds the demo user account)*

```bash
docker compose exec backend python scripts/ingest_openchargemap.py
```
*(downloads real London EV charging station data — requires the API key from step 2)*

```bash
docker compose exec backend python -m scripts.seed_background_reservations
```
*(adds background bookings so the queue algorithms have realistic data to work with)*

---

## Running it (after the first setup)

Next time you want to start the app, just run:

```bash
docker compose up
```

No `--build` needed, and no need to re-run the setup commands. It will start in under a minute.

To stop everything:

```bash
docker compose down
```

---

## Opening the app

Once running, open your browser and go to:

- **App:** http://localhost:5173
- **API documentation:** http://localhost:8000/docs

**Demo login credentials:**
- Email: `demo.user@example.com`
- Password: `DemoPass123!`

---

## What to do in the app

1. Log in with the demo credentials above
2. You'll see a map of London with charging station markers
3. The app will ask for your current location — allow it, or it defaults to central London
4. Select a **scheduling algorithm** from the dropdown:
   - **Nearest** — picks the closest station by road distance
   - **Dijkstra** — shortest path on a simplified road graph
   - **Static Queue** — factors in predicted queue wait time (Erlang-C formula)
   - **Queue Aware** — same as above but accounts for upcoming bookings in your arrival window
   - **Cost Optimised** — balances distance, wait time, and price
   - **Range Aware** — only shows stations reachable on your current battery level
5. The top recommendations appear ranked — click one to see details and book a slot

---

## Project structure

```
backend/          FastAPI backend (Python)
  app/
    algorithms.py   All six scheduling algorithms
    main.py         API routes
    models.py       Database models
  experiments/      Statistical experiment scripts + results (CSVs)
  tests/            Unit and integration tests

frontend/         React + Leaflet map UI
  src/
    App.jsx         Main app component
    api.js          API client

docker-compose.yml  Orchestrates all services
```

---

## Running the tests

```bash
docker compose exec backend pytest -q
```

---

## Troubleshooting

**"Port already in use" error:**
Something else is using port 5173, 8000, or 5432. Stop other Docker containers or services on those ports, then try again.

**Containers crash immediately:**
Make sure Docker Desktop is open and running before you run `docker compose up`.

**Map loads but no stations appear:**
The seed step may not have run. Run the four setup commands from Step 4 again.

**OSRM keeps re-downloading:**
This was a known bug — it has been fixed. If you pulled an older version, update with `git pull` and try again.
