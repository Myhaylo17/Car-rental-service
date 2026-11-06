from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent / ".env",
        extra="ignore",
        frozen=True,
    )
    app_name: str = "Car Rental API"
    mysql_host: str = "127.0.0.1"
    mysql_port: int = Field(default=3306, ge=1, le=65535)
    mysql_database: str = "car_rental"
    mysql_user: str = "car_rental_app"
    mysql_password: SecretStr
    jwt_secret_key: SecretStr = Field(min_length=32)
    jwt_algorithm: Literal["HS256"] = "HS256"
    jwt_issuer: str = "car-rental-api"
    jwt_audience: str = "car-rental-client"
    access_token_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_days: int = Field(default=7, ge=1, le=30)
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]
    rate_limit_max_keys: int = Field(default=10000, ge=100, le=100000)
    email_backend: Literal["console", "smtp"] = "console"
    google_api_key: SecretStr = SecretStr("")
    google_model: str = ""
    # Per-attempt HTTP deadline for one Gemini call (SDK retries once on 429/5xx).
    google_timeout_seconds: int = Field(default=20, ge=5, le=55)
    # Gemini 3.x thinks by default; "low" is enough for filter/ID extraction.
    # Empty string omits the setting (for models without thinking_level).
    google_thinking_level: Literal["", "low", "medium", "high"] = "low"
    app_env: str = "development"
    # Used only by `python -m src.seed`; never stored or logged.
    seed_user_password: SecretStr = SecretStr("")
    smtp_host: str = "127.0.0.1"
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_starttls: bool = False
    smtp_use_tls: bool = False
    mail_from: str = "bookings@rental.local"

    @model_validator(mode="after")
    def validate_security(self) -> "Settings":
        secret = self.jwt_secret_key.get_secret_value()
        if "replace" in secret.lower() or len(set(secret)) < 10:
            raise ValueError(
                "Generate a random JWT_SECRET_KEY; placeholders are forbidden."
            )
        if self.smtp_starttls and self.smtp_use_tls:
            raise ValueError("Choose SMTP STARTTLS or implicit TLS, not both.")
        return self

    @property
    def database_url(self) -> URL:
        return URL.create(
            "mysql+asyncmy",
            username=self.mysql_user,
            password=self.mysql_password.get_secret_value(),
            host=self.mysql_host,
            port=self.mysql_port,
            database=self.mysql_database,
            query={"charset": "utf8mb4"},
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
