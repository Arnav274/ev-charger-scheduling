"""Book up the largest stations for the coming hour, to show queue_aware steering around them.

The bookings belong to a separate account that cannot sign in, so the demo
user's own booking allowance is left free.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.database import SessionLocal

BACKGROUND_USER_ID = "b0000001-0000-4000-8000-000000000001"
BACKGROUND_USER_EMAIL = "background.bookings@example.com"


def next_full_hour_utc(now: datetime) -> datetime:
    now = now.astimezone(UTC)
    return now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


def main() -> None:
    db = SessionLocal()
    try:
        # No password hash, so nobody can sign in as this account.
        db.execute(
            text("INSERT INTO users (id, email) VALUES (:id, :email) ON CONFLICT (email) DO NOTHING"),
            {"id": BACKGROUND_USER_ID, "email": BACKGROUND_USER_EMAIL},
        )
        user_id = db.execute(
            text("SELECT id FROM users WHERE email = :email"), {"email": BACKGROUND_USER_EMAIL}
        ).scalar_one()

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

        anchor = next_full_hour_utc(datetime.now(UTC))
        # Book every charger at these stations for 75 minutes from the next full
        # hour, staggered by up to 25 minutes, so a request arriving then finds
        # them fully booked and queue_aware steers away while static_queue does not.
        # Slots someone has already booked are skipped rather than failing the seed.
        for idx, row in enumerate(charger_rows):
            charger_id = str(row.id)
            start = anchor + timedelta(minutes=(idx % 6) * 5)
            end = start + timedelta(minutes=75)
            db.execute(
                text(
                    """
                    INSERT INTO reservations (id, charger_id, user_id, start_time, end_time)
                    VALUES (:id, :charger_id, :user_id, :start_time, :end_time)
                    ON CONFLICT DO NOTHING
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
