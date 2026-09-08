"""Assembling a pulse: fetch, normalise, compare, describe.

This is the only module that knows the order of operations. The layers below it
are independently testable — the client speaks HTTP, the domain does arithmetic
— and this is where they are wired together.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from app.config import Settings
from app.domain.insights import (
    MetricChange,
    WindowBounds,
    compare,
    resolve_anchor,
    resolve_windows,
    select_headline,
)
from app.domain.metrics import ALL_METRICS, MetricKey, build_all_series
from app.domain.series import DailySeries
from app.junction.source import HealthDataSource, SourceDescriptor, provider_label

# Extra days fetched beyond the analysis window, so a device that has not synced
# for a few days still has a full window of history behind its last reading.
SYNC_SLACK_DAYS = 7


@dataclass(frozen=True)
class Patient:
    """The demo patient and their provider connection."""

    name: str
    provider: str
    provider_label: str
    is_connected: bool
    connection_status: str


@dataclass(frozen=True)
class Pulse:
    """Everything the UI needs for one render, computed server-side.

    The evidence view is assembled here rather than in the browser, so the
    numbers shown and the numbers explained cannot diverge.
    """

    patient: Patient
    source: SourceDescriptor
    anchor: date
    bounds: WindowBounds
    changes: dict[MetricKey, MetricChange]
    headline: MetricChange | None
    trends: dict[MetricKey, DailySeries]
    generated_at: datetime
    # The threshold every comparison in `changes` was made against. Carried here
    # so callers describing the analysis do not have to reach into an arbitrary
    # metric to recover a parameter that applies to all of them.
    threshold_pct: float


class PulseService:
    """Builds a :class:`Pulse` from any :class:`HealthDataSource`."""

    def __init__(self, source: HealthDataSource, settings: Settings) -> None:
        self._source = source
        self._settings = settings

    async def build(self, today: date | None = None) -> Pulse:
        today = today or datetime.now(UTC).date()
        settings = self._settings

        # Fetch generously: the analysis window, enough history for the trend
        # chart, and slack for a device that is behind on syncing. Asking
        # Junction for days it has no data for simply returns fewer records.
        lookback = max(settings.trend_days, settings.total_window_days) + SYNC_SLACK_DAYS
        fetch_start = today - timedelta(days=lookback - 1)

        sessions = await self._source.fetch_sleep(fetch_start, today)
        activity = await self._source.fetch_activity(fetch_start, today)

        series = build_all_series(fetch_start, today, sessions, activity)

        anchor = resolve_anchor(series, fallback=today)
        bounds = resolve_windows(anchor, settings.baseline_days, settings.recent_days)

        changes = {
            metric.key: compare(
                metric,
                series[metric.key],
                bounds,
                threshold_pct=settings.change_threshold_pct,
                min_coverage_ratio=settings.min_coverage_ratio,
            )
            for metric in ALL_METRICS
        }

        trend_start = anchor - timedelta(days=settings.trend_days - 1)
        trends = {key: value.window(trend_start, anchor) for key, value in series.items()}

        return Pulse(
            patient=self._patient(),
            source=self._source.describe(),
            anchor=anchor,
            bounds=bounds,
            changes=changes,
            headline=select_headline(changes),
            trends=trends,
            generated_at=datetime.now(UTC),
            threshold_pct=settings.change_threshold_pct,
        )

    def _patient(self) -> Patient:
        descriptor = self._source.describe()
        return Patient(
            name=self._settings.demo_patient_name,
            provider=descriptor.provider,
            provider_label=provider_label(descriptor.provider),
            is_connected=descriptor.is_live,
            # Never claim a live device connection for generated data.
            connection_status="Connected" if descriptor.is_live else "Demo data",
        )
