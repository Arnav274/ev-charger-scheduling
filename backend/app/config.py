import logging
import os

# Queueing and energy model parameters. Sources and sensitivity ranges are in
# docs/parameter_justification.md.
ARRIVAL_RATE_PER_HOUR_DEFAULT: float = 0.75  # Hecht et al. (2022)
MEAN_SERVICE_MINUTES_DEFAULT: float = 40.0  # DoE EERE FOTW #1319 (2023)
ENERGY_CONSUMPTION_KWH_PER_KM: float = 0.2  # Weiss et al. (2024)

DEV_JWT_SECRET = "dev-only-secret-do-not-use-in-production"

logger = logging.getLogger(__name__)


class Settings:
    def __init__(self) -> None:
        # The fallback URL is for running the backend outside Compose: 5433 is the
        # host port the db service publishes. Inside Compose DATABASE_URL is set.
        self.database_url = os.getenv(
            "DATABASE_URL", "postgresql+psycopg2://evuser:evpass@localhost:5433/evdb"
        )
        self.osrm_base_url = os.getenv("OSRM_BASE_URL", "http://osrm:5000")
        self.jwt_secret_key = os.getenv("JWT_SECRET_KEY") or DEV_JWT_SECRET
        self.jwt_algorithm = "HS256"
        self.jwt_expire_minutes = int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))

        if self.jwt_secret_key == DEV_JWT_SECRET:
            logger.warning(
                "JWT_SECRET_KEY is not set; using the development secret. Set it outside local dev."
            )


settings = Settings()
