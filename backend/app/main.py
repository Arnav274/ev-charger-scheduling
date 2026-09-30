from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth, recommendations, reservations, stations, stats, vehicles

app = FastAPI(title="EV Charger Scheduling")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (auth, stations, reservations, vehicles, recommendations, stats):
    app.include_router(module.router)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
