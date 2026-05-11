"""initial schema with postgis and exclusion constraint

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-02 17:30:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist;")

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "vehicles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("make_model", sa.String(length=120), nullable=False),
        sa.Column("battery_kwh", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "stations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="openchargemap"),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("borough", sa.String(length=80), nullable=True),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("price_pence_per_kwh", sa.Float(), nullable=False, server_default="55"),
        sa.Column("arrival_rate_per_hour", sa.Float(), nullable=False, server_default="4"),
        sa.Column("mean_service_minutes", sa.Float(), nullable=False, server_default="40"),
        sa.Column("raw_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id"),
    )
    op.create_table(
        "chargers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("station_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("power_kw", sa.Float(), nullable=False, server_default="22"),
        sa.Column("connector_type", sa.String(length=80), nullable=False, server_default="Type2"),
        sa.ForeignKeyConstraint(["station_id"], ["stations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("charger_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("start_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("end_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["charger_id"], ["chargers.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.execute("ALTER TABLE stations ADD COLUMN location geography(Point,4326);")
    op.execute(
        """
        UPDATE stations
        SET location = ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography;
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_stations_location_gist ON stations USING GIST (location);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_reservations_timerange_gist ON reservations USING GIST (tstzrange(start_time, end_time));")
    op.execute(
        """
        ALTER TABLE reservations
        ADD CONSTRAINT exclude_overlapping_reservations
        EXCLUDE USING GIST (
            charger_id WITH =,
            tstzrange(start_time, end_time) WITH &&
        );
        """
    )


def downgrade() -> None:
    op.drop_table("reservations")
    op.drop_table("chargers")
    op.drop_table("stations")
    op.drop_table("vehicles")
    op.drop_table("users")
