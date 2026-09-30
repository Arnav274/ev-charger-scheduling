"""derive stations.location from lat/lon

The geography column used to be written by hand alongside lat and lon, so the
two could drift apart and ORM inserts left it NULL. A stored generated column
keeps it in step automatically.

Revision ID: 0003_generated_station_location
Revises: 0002_user_password_hash
Create Date: 2026-09-30
"""

from alembic import op

revision = "0003_generated_station_location"
down_revision = "0002_user_password_hash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_stations_location_gist;")
    op.execute("ALTER TABLE stations DROP COLUMN location;")
    op.execute(
        """
        ALTER TABLE stations ADD COLUMN location geography(Point, 4326)
        GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography) STORED;
        """
    )
    op.execute("CREATE INDEX idx_stations_location_gist ON stations USING GIST (location);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_stations_location_gist;")
    op.execute("ALTER TABLE stations DROP COLUMN location;")
    op.execute("ALTER TABLE stations ADD COLUMN location geography(Point, 4326);")
    op.execute("UPDATE stations SET location = ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography;")
    op.execute("CREATE INDEX idx_stations_location_gist ON stations USING GIST (location);")
