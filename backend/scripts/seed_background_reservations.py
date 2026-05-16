"""
Seed deterministic future reservations to create a reproducible 'hotspot' for demos and screenshots.

This is intentionally simple: it creates many overlapping reservations across multiple chargers
at a small number of stations, so `queue_aware` (predictive) diverges clearly from `static_queue`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.database import SessionLocal


DEMO_USER_EMAIL = "demo.user@example.com"


def next_full_hour_utc(now: datetime) -> datetime:
    now = now.astimezone(timezone.utc)
    return (now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))


def main() -> None:
    db = SessionLocal()
    try:
        user_id = db.execute(
            text("SELECT id FROM users WHERE email = :email"),
            {"email": DEMO_USER_EMAIL},
        ).scalar()
        if user_id is None:
            raise RuntimeError(
                f"Demo user not found ({DEMO_USER_EMAIL}). Run `python -m scripts.seed_demo` first."
            )

        # Pick a small set of stations with the most chargers to make the hotspot visually obvious.
        station_rows = db.execute(
            text(
                """
                SELECT s.id
                FROM stations s
                JOIN chargers c ON c.station_id = s.id
                GROUP BY s.id
                ORDER BY COUNT(*) DESC, s.id ASC
                LIMIT 3
                """
            )
        ).all()
        if not station_rows:
            raise RuntimeError("No stations/chargers found. Run ingestion first.")

        station_ids = [str(r.id) for r in station_rows]
        for sid in station_ids:
            uuid.UUID(sid)
        charger_rows = db.execute(
            text(
                """
                SELECT c.id, c.station_id
                FROM chargers c
                WHERE c.station_id = ANY(CAST(:station_ids AS uuid[]))
                ORDER BY c.station_id ASC, c.id ASC
                """
            ),
            {"station_ids": station_ids},
        ).all()

        # Clear prior demo hotspot reservations for determinism.
        db.execute(
            text(
                """
                DELETE FROM reservations
                WHERE user_id = :user_id
                  AND charger_id IN (
                    SELECT id FROM chargers WHERE station_id = ANY(CAST(:station_ids AS uuid[]))
                  )
                """
            ),
            {"user_id": user_id, "station_ids": station_ids},
        )

        anchor = next_full_hour_utc(datetime.now(timezone.utc))
        # Create heavy overlap for ~90 minutes, with multiple starts inside the arrival window.
        # This increases both reserved_parallel and reservation_starts.
        for idx, row in enumerate(charger_rows):
            charger_id = str(row.id)
            # Stagger starts slightly across chargers to create starts within windows too.
            start = anchor + timedelta(minutes=(idx % 6) * 5)
            end = start + timedelta(minutes=75)
            db.execute(
                text(
                    """
                    INSERT INTO reservations (id, charger_id, user_id, start_time, end_time)
                    VALUES (:id, :charger_id, :user_id, :start_time, :end_time)
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "charger_id": charger_id,
                    "user_id": str(user_id),
                    "start_time": start,
                    "end_time": end,
                },
            )

        db.commit()

        # Print reproducible demo parameters.
        demo_origin = {"lat": 51.5074, "lon": -0.1278}  # central London
        print("Seeded background reservations for hotspot demo.")
        print(f"Hotspot stations: {station_ids}")
        print("Suggested demo request payload:")
        print(
            {
                "origin_lat": demo_origin["lat"],
                "origin_lon": demo_origin["lon"],
                "radius_km": 5,
                "top_k": 5,
                "arrival_time_target": anchor.isoformat(),
                "arrival_window_minutes": 30,
                "algorithm": "queue_aware",
            }
        )
        print("Compare with algorithm='static_queue' to show divergence.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

