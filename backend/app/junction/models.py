"""Pydantic models for the subset of Junction's API this service consumes.

Two deliberate choices:

``extra="ignore"``
    Junction's summary payloads carry far more fields than Health Pulse uses,
    and more can be added over time. Binding only what is needed means a
    provider gaining a new field cannot break parsing.

Optional almost everywhere
    Junction normalises across 300+ devices, and coverage differs by provider:
    a Fitbit night and an Oura night do not populate the same columns. Every
    measurement is therefore ``| None`` and handled as genuinely absent rather
    than defaulted to zero.

Schema reference: https://docs.junction.com/api-reference/data/sleep/get-summary
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class JunctionModel(BaseModel):
    """Base for Junction payloads: tolerant of unknown fields, alias-aware."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class Source(JunctionModel):
    """Where a measurement came from.

    Junction reports the upstream provider per record, which is what lets the UI
    attribute a number to "Fitbit via Junction" rather than to Junction alone.
    """

    provider: str
    source_type: str | None = Field(default=None, alias="type")
    app_id: str | None = None
    device_id: str | None = None


class SleepSummary(JunctionModel):
    """One sleep session as returned by ``GET /v2/summary/sleep/{user_id}``."""

    id: str | None = None
    user_id: str | None = None
    calendar_date: date
    bedtime_start: datetime | None = None
    bedtime_stop: datetime | None = None
    sleep_type: str | None = Field(default=None, alias="type")

    # Durations in seconds. `duration` is time in bed; `total` is time asleep.
    duration: int | None = None
    total: int | None = None
    awake: int | None = None
    light: int | None = None
    rem: int | None = None
    deep: int | None = None

    score: int | None = None
    efficiency: float | None = None
    latency: int | None = None

    # Junction exposes three heart-rate readings per night and providers do not
    # populate them consistently; see domain.metrics for the resolution order.
    hr_lowest: int | None = None
    hr_average: int | None = None
    hr_resting: int | None = None

    average_hrv: float | None = None
    respiratory_rate: float | None = None

    source: Source | None = None


class ActivityHeartRate(JunctionModel):
    """Daily heart-rate rollup nested inside an activity summary."""

    avg_bpm: float | None = None
    min_bpm: float | None = None
    max_bpm: float | None = None
    resting_bpm: float | None = None
    avg_walking_bpm: float | None = None


class ActivitySummary(JunctionModel):
    """One day of activity from ``GET /v2/summary/activity/{user_id}``."""

    id: str | None = None
    user_id: str | None = None
    calendar_date: date

    steps: int | None = None
    calories_total: float | None = None
    calories_active: float | None = None
    distance: float | None = None
    floors_climbed: int | None = None

    heart_rate: ActivityHeartRate | None = None
    source: Source | None = None


class SleepResponse(JunctionModel):
    """Envelope returned by the sleep summary endpoint."""

    sleep: list[SleepSummary] = Field(default_factory=list)


class ActivityResponse(JunctionModel):
    """Envelope returned by the activity summary endpoint."""

    activity: list[ActivitySummary] = Field(default_factory=list)


class JunctionUser(JunctionModel):
    """Result of ``POST /v2/user/``."""

    user_id: str
    client_user_id: str | None = None


class DemoConnection(JunctionModel):
    """Result of ``POST /v2/link/connect/demo``."""

    success: bool
    detail: str | None = None
