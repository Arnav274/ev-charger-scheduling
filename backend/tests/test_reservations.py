from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal


@pytest.mark.integration
def test_overlapping_reservation_rejected() -> None:
    db = SessionLocal()
    ids = None
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("Database not available for integration test.")

    try:
        ids = db.execute(
            text(
                """
                WITH u AS (
                    INSERT INTO users (id, email) VALUES (:user_id, :email) RETURNING id
                ),
                s AS (
                    INSERT INTO stations (
                        id, source, source_id, name, lat, lon, location, price_pence_per_kwh,
                        arrival_rate_per_hour, mean_service_minutes, raw_json
                    )
                    VALUES (
                        :station_id, 'test', :sid, 'Test Station', 51.5, -0.12,
                        ST_SetSRID(ST_MakePoint(-0.12, 51.5), 4326)::geography, 50, 4, 40, '{}'::json
                    )
                    ON CONFLICT (source_id) DO UPDATE SET name = EXCLUDED.name
                    RETURNING id
                ),
                c AS (
                    INSERT INTO chargers (id, station_id, name, power_kw, connector_type)
                    VALUES (:charger_id, (SELECT id FROM s), 'C1', 22, 'Type2') RETURNING id
                )
                SELECT
                    (SELECT id FROM u) AS user_id,
                    (SELECT id FROM s) AS station_id,
                    (SELECT id FROM c) AS charger_id;
                """
            ),
            {
                "email": f"test_{datetime.now().timestamp()}@example.com",
                "sid": f"sid_{datetime.now().timestamp()}",
                "user_id": str(uuid4()),
                "station_id": str(uuid4()),
                "charger_id": str(uuid4()),
            },
        ).first()

        start = datetime.now(timezone.utc).replace(microsecond=0)
        end = start + timedelta(hours=1)
        db.execute(
            text(
                """
                INSERT INTO reservations (id, charger_id, user_id, start_time, end_time)
                VALUES (:reservation_id, :charger_id, :user_id, :start_t, :end_t)
                """
            ),
            {
                "reservation_id": str(uuid4()),
                "charger_id": ids.charger_id,
                "user_id": ids.user_id,
                "start_t": start,
                "end_t": end,
            },
        )
        db.commit()

        with pytest.raises(IntegrityError):
            db.execute(
                text(
                    """
                    INSERT INTO reservations (id, charger_id, user_id, start_time, end_time)
                    VALUES (:reservation_id, :charger_id, :user_id, :start_t, :end_t)
                    """
                ),
                {
                    "reservation_id": str(uuid4()),
                    "charger_id": ids.charger_id,
                    "user_id": ids.user_id,
                    "start_t": start + timedelta(minutes=30),
                    "end_t": end + timedelta(minutes=30),
                },
            )
            db.commit()
    finally:
        db.rollback()
        if ids is not None:
            db.execute(text("DELETE FROM reservations WHERE charger_id = :charger_id"), {"charger_id": ids.charger_id})
            db.execute(text("DELETE FROM chargers WHERE id = :charger_id"), {"charger_id": ids.charger_id})
            db.execute(text("DELETE FROM stations WHERE id = :station_id"), {"station_id": ids.station_id})
            db.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": ids.user_id})
            db.commit()
        db.close()
