"""Application configuration.

All tunable behaviour lives here rather than being scattered as literals through
the codebase, so the analysis window and change threshold can be reviewed (and
changed) in one place.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DataSource = Literal["auto", "live", "fixture"]

# Providers for which Junction's sandbox generates synthetic data.
# https://docs.junction.com/wearables/providers/test_data
DEMO_PROVIDERS = ("apple_health_kit", "fitbit", "freestyle_libre", "oura")


class Settings(BaseSettings):
    """Environment-backed settings, read once at startup."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Junction ------------------------------------------------------------
    junction_api_key: str | None = None
    junction_base_url: str = "https://api.sandbox.us.junction.com"
    junction_user_id: str | None = None
    junction_client_user_id: str = "health-pulse-demo-patient"
    junction_provider: str = "fitbit"
    junction_timeout_seconds: float = 10.0
    junction_max_retries: int = 2

    # --- Data source ---------------------------------------------------------
    health_pulse_data_source: DataSource = "auto"

    # --- Analysis window -----------------------------------------------------
    # Junction backfills 30 days of history for a demo connection, so a 21-day
    # baseline plus a 7-day recent window fits inside what the sandbox provides.
    baseline_days: int = Field(default=21, ge=1)
    recent_days: int = Field(default=7, ge=1)

    # A metric must move by more than this percentage before it is reported as
    # increased or decreased. Prototype threshold, not a clinical one.
    change_threshold_pct: float = Field(default=10.0, gt=0)

    # Fraction of days in a window that must carry a measurement before a
    # comparison is considered trustworthy enough to report.
    min_coverage_ratio: float = Field(default=0.7, ge=0, le=1)

    # --- Presentation --------------------------------------------------------
    demo_patient_name: str = "Demo Patient"
    trend_days: int = Field(default=30, ge=1)

    # --- HTTP ----------------------------------------------------------------
    health_pulse_cors_origins: str = "http://localhost:3000"

    @field_validator("junction_provider")
    @classmethod
    def _known_demo_provider(cls, value: str) -> str:
        if value not in DEMO_PROVIDERS:
            allowed = ", ".join(DEMO_PROVIDERS)
            raise ValueError(f"junction_provider must be one of: {allowed}")
        return value

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip() for origin in self.health_pulse_cors_origins.split(",") if origin.strip()
        ]

    @property
    def total_window_days(self) -> int:
        """Days of history needed to compute a baseline and a recent window."""
        return self.baseline_days + self.recent_days

    @property
    def junction_is_configured(self) -> bool:
        return bool(self.junction_api_key)

    @property
    def use_fixtures(self) -> bool:
        """Whether to serve locally generated data instead of calling Junction.

        In ``auto`` mode the service falls back to fixtures when Junction has not
        been configured, so the app is runnable straight after a clone.
        """
        if self.health_pulse_data_source == "fixture":
            return True
        if self.health_pulse_data_source == "live":
            return False
        return not (self.junction_is_configured and self.junction_user_id)


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor, used as a FastAPI dependency."""
    return Settings()
