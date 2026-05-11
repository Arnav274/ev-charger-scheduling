import os


class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg2://evuser:evpass@localhost:5432/evdb"
    )
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "dev-change-me-do-not-use-in-production")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))


settings = Settings()
