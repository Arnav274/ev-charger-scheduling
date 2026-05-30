import os

# Model parameters, defaults used in seeding and strategies.
# Full citations in docs/parameter_justification.md.

ARRIVAL_RATE_PER_HOUR_DEFAULT: float = 0.75   # Hecht et al. (2022)
MEAN_SERVICE_MINUTES_DEFAULT: float = 40.0    # DoE EERE FOTW #1319 (2023)
ENERGY_CONSUMPTION_KWH_PER_KM: float = 0.2   # Weiss et al. (2024)


class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg2://evuser:evpass@localhost:5432/evdb"
    )
    osrm_base_url: str = os.getenv("OSRM_BASE_URL", "http://osrm:5000")
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "dev-change-me-do-not-use-in-production")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))


settings = Settings()
