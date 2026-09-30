"""Shared fixtures.

API tests run against a real PostGIS database, so the spatial queries and the
double-booking exclusion constraint are exercised for real. They use a separate
`<name>_test` database on the same server, migrated with Alembic once per run.
Each test runs inside a transaction that is rolled back afterwards; commits made
by the endpoints become savepoints within it.

Without a reachable database those tests are skipped, unless REQUIRE_DB=1 (set
in CI), in which case they fail instead.
"""

import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

_BASE_URL = make_url(
    os.environ.get("DATABASE_URL", "postgresql+psycopg2://evuser:evpass@localhost:5433/evdb")
)
TEST_DB_URL = _BASE_URL.set(database=f"{_BASE_URL.database}_test")
# The app reads DATABASE_URL at import time, so point it at the test database first.
os.environ["DATABASE_URL"] = TEST_DB_URL.render_as_string(hide_password=False)

from fastapi.testclient import TestClient  # noqa: E402

from app.auth_utils import create_access_token, hash_password  # noqa: E402
from app.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Charger, Station, User  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _create_test_database() -> None:
    admin = create_engine(_BASE_URL.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            exists = conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": TEST_DB_URL.database}
            )
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{TEST_DB_URL.database}"'))
    finally:
        admin.dispose()


@pytest.fixture(scope="session")
def db_engine():
    try:
        _create_test_database()
    except OperationalError as exc:
        if os.environ.get("REQUIRE_DB") == "1":
            raise
        pytest.skip(f"PostGIS not reachable, skipping database tests: {exc.orig}")

    from alembic import command
    from alembic.config import Config

    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    engine = create_engine(TEST_DB_URL)
    yield engine
    engine.dispose()


@pytest.fixture
def db(db_engine):
    connection = db_engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()


@pytest.fixture
def client(db):
    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def user(db) -> User:
    email = f"driver-{uuid.uuid4().hex[:8]}@example.com"
    user = User(email=email, password_hash=hash_password("Password123"))
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def auth_headers(user) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.fixture
def make_station(db):
    def _make(
        *,
        lat: float = 51.5074,
        lon: float = -0.1278,
        chargers: int = 2,
        name: str | None = None,
        price: float = 55.0,
        arrival_rate: float = 0.75,
    ) -> Station:
        sid = uuid.uuid4()
        station = Station(
            id=sid,
            source="test",
            source_id=f"test-{sid}",
            name=name or f"Station {sid.hex[:6]}",
            borough="Westminster",
            address="1 Test Street",
            lat=lat,
            lon=lon,
            price_pence_per_kwh=price,
            arrival_rate_per_hour=arrival_rate,
            mean_service_minutes=40.0,
            raw_json={},
        )
        station.chargers = [Charger(name=f"C{i + 1}") for i in range(chargers)]
        db.add(station)
        db.flush()
        return station

    return _make


@pytest.fixture
def now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)
