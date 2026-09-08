"""API response models.

Deliberately separate from the domain dataclasses. The domain is free to change
shape; the wire format is a contract the frontend is typed against. Translating
between them here means a refactor in app.domain cannot silently break the UI —
it breaks this file first, which is where a reviewer would look.
"""

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.domain.insights import (
    ChangeDirection,
    InsufficientReason,
    MetricChange,
    WindowSummary,
)
from app.domain.metrics import MetricKey, MetricUnit
from app.domain.narrative import (
    DISCLAIMER,
    HEADLINE_TITLE,
    NO_CHANGE_BODY,
    NO_CHANGE_TITLE,
    describe_change,
    short_verdict,
)
from app.domain.series import Coverage, DailySeries
from app.services.pulse import Pulse


class CoverageOut(BaseModel):
    """How much of a window carried a measurement."""

    observed_days: int
    expected_days: int
    ratio: float = Field(description="observed_days / expected_days, 0.0 to 1.0")

    @classmethod
    def of(cls, coverage: Coverage) -> "CoverageOut":
        return cls(
            observed_days=coverage.observed_days,
            expected_days=coverage.expected_days,
            ratio=round(coverage.ratio, 4),
        )


class WindowOut(BaseModel):
    """One side of the comparison."""

    label: str
    start_date: date
    end_date: date
    mean: float | None = Field(description="Mean over observed days only; null if none were.")
    coverage: CoverageOut


class DerivationOut(BaseModel):
    """Which upstream field produced a metric, and on how many days."""

    field_name: str = Field(serialization_alias="field")
    days: int

    model_config = {"populate_by_name": True}


class MetricChangeOut(BaseModel):
    """A metric's recent behaviour, plus everything needed to justify it.

    The evidence fields are not optional extras: an insight the reader cannot
    check is the thing this project set out to avoid.
    """

    key: MetricKey
    label: str
    unit: MetricUnit
    description: str

    direction: ChangeDirection
    verdict: str = Field(description="Two-word summary for the metric card.")
    summary: str = Field(description="One sentence stating what the data shows.")

    latest_value: float | None
    latest_day: date | None
    pct_change: float | None
    absolute_change: float | None

    threshold_pct: float
    insufficient_reason: InsufficientReason | None
    baseline: WindowOut
    recent: WindowOut
    derivations: list[DerivationOut]

    @classmethod
    def of(cls, change: MetricChange) -> "MetricChangeOut":
        return cls(
            key=change.metric.key,
            label=change.metric.label,
            unit=change.metric.unit,
            description=change.metric.description,
            direction=change.direction,
            verdict=short_verdict(change),
            summary=describe_change(change),
            latest_value=change.latest_value,
            latest_day=change.latest_day,
            pct_change=round(change.pct_change, 2) if change.pct_change is not None else None,
            absolute_change=(
                round(change.absolute_change, 2) if change.absolute_change is not None else None
            ),
            threshold_pct=change.threshold_pct,
            insufficient_reason=change.insufficient_reason,
            baseline=_window(change.baseline),
            recent=_window(change.recent),
            derivations=[
                DerivationOut(field_name=name, days=days)
                for name, days in sorted(
                    (change.derivations or {}).items(), key=lambda item: (-item[1], item[0])
                )
            ],
        )


class TrendPointOut(BaseModel):
    """One day on the chart. ``value`` is null for a day with no measurement."""

    day: date
    value: float | None


class TrendOut(BaseModel):
    key: MetricKey
    label: str
    unit: MetricUnit
    points: list[TrendPointOut]
    coverage: CoverageOut

    @classmethod
    def of(cls, change: MetricChange, series: DailySeries) -> "TrendOut":
        return cls(
            key=change.metric.key,
            label=change.metric.label,
            unit=change.metric.unit,
            points=[TrendPointOut(day=p.day, value=p.value) for p in series.points],
            coverage=CoverageOut.of(series.coverage),
        )


class PatientOut(BaseModel):
    name: str
    provider: str
    provider_label: str
    is_connected: bool
    connection_status: str


class SourceOut(BaseModel):
    """Provenance, shown to the user verbatim."""

    provider: str
    mode: str = Field(description="'junction' for live API data, 'fixture' for generated data.")
    label: str = Field(description="Attribution string, e.g. 'Fitbit via Junction'.")
    is_live: bool


class WindowSpecOut(BaseModel):
    """The analysis window, so the UI never has to restate the parameters."""

    anchor_date: date = Field(description="Last day with data; the window ends here, not today.")
    baseline_days: int
    recent_days: int
    baseline_start: date
    baseline_end: date
    recent_start: date
    recent_end: date


class HeadlineOut(BaseModel):
    """The single change worth surfacing, or the reason there isn't one.

    Populated in both cases rather than left null when nothing moved: "no
    notable changes" is itself a finding, and the reader should see it stated.
    """

    title: str
    body: str
    metric: MetricKey | None = None


class PulseOut(BaseModel):
    """The full payload behind one render of the dashboard."""

    patient: PatientOut
    source: SourceOut
    window: WindowSpecOut
    headline: HeadlineOut
    metrics: list[MetricChangeOut]
    trends: list[TrendOut]
    generated_at: datetime
    disclaimer: str = DISCLAIMER

    @classmethod
    def of(cls, pulse: Pulse) -> "PulseOut":
        if pulse.headline is not None:
            headline = HeadlineOut(
                title=HEADLINE_TITLE,
                body=describe_change(pulse.headline),
                metric=pulse.headline.metric.key,
            )
        else:
            sleep_change = pulse.changes[MetricKey.SLEEP]
            headline = HeadlineOut(
                title=NO_CHANGE_TITLE,
                body=NO_CHANGE_BODY.format(
                    threshold=sleep_change.threshold_pct,
                    baseline_days=sleep_change.baseline.coverage.expected_days,
                ),
            )

        return cls(
            patient=PatientOut(**vars(pulse.patient)),
            source=SourceOut(
                provider=pulse.source.provider,
                mode=pulse.source.mode,
                label=pulse.source.label,
                is_live=pulse.source.is_live,
            ),
            window=WindowSpecOut(
                anchor_date=pulse.anchor,
                baseline_days=pulse.changes[MetricKey.SLEEP].baseline.coverage.expected_days,
                recent_days=pulse.changes[MetricKey.SLEEP].recent.coverage.expected_days,
                baseline_start=pulse.bounds.baseline_start,
                baseline_end=pulse.bounds.baseline_end,
                recent_start=pulse.bounds.recent_start,
                recent_end=pulse.bounds.recent_end,
            ),
            headline=headline,
            metrics=[MetricChangeOut.of(change) for change in pulse.changes.values()],
            trends=[
                TrendOut.of(pulse.changes[key], series) for key, series in pulse.trends.items()
            ],
            generated_at=pulse.generated_at,
        )


class ProvisionResultOut(BaseModel):
    """Outcome of creating a Junction demo patient."""

    user_id: str
    provider: str
    connected: bool
    detail: str | None
    next_step: str


def _window(summary: WindowSummary) -> WindowOut:
    """Translate a domain window summary into its wire representation."""
    return WindowOut(
        label=summary.label,
        start_date=summary.start,
        end_date=summary.end,
        mean=round(summary.mean, 2) if summary.mean is not None else None,
        coverage=CoverageOut.of(summary.coverage),
    )
