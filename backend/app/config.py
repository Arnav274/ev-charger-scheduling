import os

# ---------------------------------------------------------------------------
# Model parameters — values used as defaults in seeding and strategies.
# See docs/parameter_justification.md for full citations and sensitivity notes.
# ---------------------------------------------------------------------------

# Hecht, C., Figgener, J., & Sauer, D.U. (2022). Analysis of electric vehicle
# charging station usage and profitability in Germany based on empirical data.
# iScience, 25(12), 105634. https://doi.org/10.1016/j.isci.2022.105634
ARRIVAL_RATE_PER_HOUR_DEFAULT: float = 4.0

# U.S. Department of Energy, EERE. (2023, December 4). FOTW #1319: EV Charging
# at Paid DC Fast Charging Stations Average 42 Minutes per Session (2.4 M
# sessions, Energetics/EVWATTS Dashboard).
# https://www.energy.gov/eere/vehicles/articles/fotw-1319-december-4-2023-ev-charging-paid-dc-fast-charging-stations-average
MEAN_SERVICE_MINUTES_DEFAULT: float = 40.0

# Weiss, M., Winbush, T., Newman, A., & Helmers, E. (2024). Energy Consumption
# of Electric Vehicles in Europe. Sustainability, 16(17), 7529.
# https://doi.org/10.3390/su16177529  (real-world fleet average: 21 kWh/100 km;
# 0.20 kWh/km adopted as a conservative rounded figure)
ENERGY_CONSUMPTION_KWH_PER_KM: float = 0.2


class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg2://evuser:evpass@localhost:5432/evdb"
    )
    osrm_base_url: str = os.getenv("OSRM_BASE_URL", "http://osrm:5000")
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "dev-change-me-do-not-use-in-production")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))


settings = Settings()
