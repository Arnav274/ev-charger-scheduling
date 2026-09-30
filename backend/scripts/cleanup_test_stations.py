"""Remove integration-test station rows (source='test') from local dev DB."""

from sqlalchemy import text

from app.database import SessionLocal


def main() -> None:
    db = SessionLocal()
    try:
        db.execute(
            text(
                """
                DELETE FROM reservations
                WHERE charger_id IN (
                    SELECT id FROM chargers
                    WHERE station_id IN (SELECT id FROM stations WHERE source = 'test')
                )
                """
            )
        )
        db.execute(
            text(
                """
                DELETE FROM chargers
                WHERE station_id IN (SELECT id FROM stations WHERE source = 'test')
                """
            )
        )
        deleted = db.execute(text("DELETE FROM stations WHERE source = 'test'")).rowcount
        db.commit()
        print(f"Deleted {deleted} test stations.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
