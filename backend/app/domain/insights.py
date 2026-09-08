"""Baseline comparison.

The whole product reduces to one calculation::

    (recent mean - baseline mean) / baseline mean x 100

Deliberately arithmetic rather than a model. If the app tells someone their
sleep is down 18%, they should be able to open the evidence view and check the
figure themselves. A learned score cannot offer that, and for a prototype
handling health data, being auditable matters more than being clever.

This module is pure: no I/O, no clock, no configuration lookups. Everything it
needs arrives as an argument, which is what makes the thresholds and the
missing-data behaviour straightforward to test.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from app.domain.metrics import MetricDefinition, MetricKey
from app.domain.series import Coverage, DailySeries


class ChangeDirection(StrEnum):
    INCREASED = "increased"
    DECREASED = "decreased"
    STABLE = "stable"
    INSUFFICIENT_DATA = "insufficient_data"


class InsufficientReason(StrEnum):
    """Why a comparison could not be made.

    Distinguishing these matters: "the device wasn't worn enough" and "there is
    no history yet" are different situations for the reader, and collapsing
    both into a blank card would hide that.
    """

    NO_RECENT_DATA = "no_recent_data"
    NO_BASELINE_DATA = "no_baseline_data"
    LOW_RECENT_COVERAGE = "low_recent_coverage"
    LOW_BASELINE_COVERAGE = "low_baseline_coverage"
    ZERO_BASELINE = "zero_baseline"


@dataclass(frozen=True)
class WindowBounds:
    """The two comparison periods, back to back and non-overlapping."""

    baseline_start: date
    baseline_end: date
    recent_start: date
    recent_end: date

    @property
    def start(self) -> date:
        return self.baseline_start

    @property
    def end(self) -> date:
        return self.recent_end

    @property
    def baseline_days(self) -> int:
        return (self.baseline_end - self.baseline_start).days + 1

    @property
    def recent_days(self) -> int:
        return (self.recent_end - self.recent_start).days + 1


@dataclass(frozen=True)
class WindowSummary:
    """One period's contribution to a comparison."""

    label: str
    start: date
    end: date
    mean: float | None
    coverage: Coverage


@dataclass(frozen=True)
class MetricChange:
    """A metric's recent behaviour relative to its own baseline.

    Carries the inputs as well as the result, because the evidence view is a
    first-class output rather than an afterthought: every field the UI shows
    when explaining a number is computed here, not reconstructed later.
    """

    metric: MetricDefinition
    direction: ChangeDirection
    baseline: WindowSummary
    recent: WindowSummary
    threshold_pct: float
    pct_change: float | None = None
    absolute_change: float | None = None
    latest_value: float | None = None
    latest_day: date | None = None
    insufficient_reason: InsufficientReason | None = None
    derivations: Mapping[str, int] | None = None

    @property
    def is_notable(self) -> bool:
        """Whether this change crossed the reporting threshold."""
        return self.direction in (ChangeDirection.INCREASED, ChangeDirection.DECREASED)

    @property
    def magnitude(self) -> float:
        """Absolute percentage movement, for ranking changes against each other."""
        return abs(self.pct_change) if self.pct_change is not None else 0.0


def resolve_windows(anchor: date, baseline_days: int, recent_days: int) -> WindowBounds:
    """Place the recent and baseline windows relative to ``anchor``.

    ``anchor`` is the last day for which data exists, not today. Anchoring on
    today would pull unsynced days into the recent window and read them as a
    drop in whatever is being measured.
    """
    if baseline_days < 1 or recent_days < 1:
        raise ValueError("baseline_days and recent_days must both be at least 1")

    recent_start = anchor - timedelta(days=recent_days - 1)
    baseline_end = recent_start - timedelta(days=1)
    baseline_start = baseline_end - timedelta(days=baseline_days - 1)
    return WindowBounds(
        baseline_start=baseline_start,
        baseline_end=baseline_end,
        recent_start=recent_start,
        recent_end=anchor,
    )


def resolve_anchor(series_by_metric: Mapping[MetricKey, DailySeries], fallback: date) -> date:
    """The most recent day any metric has data for, or ``fallback`` if none do."""
    observed = [
        series.last_observed_day
        for series in series_by_metric.values()
        if series.last_observed_day is not None
    ]
    return max(observed) if observed else fallback


def compare(
    metric: MetricDefinition,
    series: DailySeries,
    bounds: WindowBounds,
    *,
    threshold_pct: float,
    min_coverage_ratio: float,
) -> MetricChange:
    """Compare a metric's recent window against its baseline."""
    baseline_series = series.window(bounds.baseline_start, bounds.baseline_end)
    recent_series = series.window(bounds.recent_start, bounds.recent_end)

    baseline = WindowSummary(
        label=f"Previous {len(baseline_series)}-day average",
        start=bounds.baseline_start,
        end=bounds.baseline_end,
        mean=baseline_series.mean(),
        coverage=baseline_series.coverage,
    )
    recent = WindowSummary(
        label=f"Recent {len(recent_series)}-day average",
        start=bounds.recent_start,
        end=bounds.recent_end,
        mean=recent_series.mean(),
        coverage=recent_series.coverage,
    )

    latest = recent_series.observed_points[-1] if recent_series.observed_points else None
    derivations = series.window(bounds.start, bounds.end).derivation_counts()

    def insufficient(reason: InsufficientReason) -> MetricChange:
        return MetricChange(
            metric=metric,
            direction=ChangeDirection.INSUFFICIENT_DATA,
            baseline=baseline,
            recent=recent,
            threshold_pct=threshold_pct,
            latest_value=latest.value if latest else None,
            latest_day=latest.day if latest else None,
            insufficient_reason=reason,
            derivations=derivations,
        )

    if recent.mean is None:
        return insufficient(InsufficientReason.NO_RECENT_DATA)
    if baseline.mean is None:
        return insufficient(InsufficientReason.NO_BASELINE_DATA)
    if recent.coverage.ratio < min_coverage_ratio:
        return insufficient(InsufficientReason.LOW_RECENT_COVERAGE)
    if baseline.coverage.ratio < min_coverage_ratio:
        return insufficient(InsufficientReason.LOW_BASELINE_COVERAGE)
    if baseline.mean == 0:
        # A percentage change from zero has no meaningful value to report.
        return insufficient(InsufficientReason.ZERO_BASELINE)

    absolute_change = recent.mean - baseline.mean
    pct_change = absolute_change / baseline.mean * 100

    if pct_change > threshold_pct:
        direction = ChangeDirection.INCREASED
    elif pct_change < -threshold_pct:
        direction = ChangeDirection.DECREASED
    else:
        direction = ChangeDirection.STABLE

    return MetricChange(
        metric=metric,
        direction=direction,
        baseline=baseline,
        recent=recent,
        threshold_pct=threshold_pct,
        pct_change=pct_change,
        absolute_change=absolute_change,
        latest_value=latest.value if latest else None,
        latest_day=latest.day if latest else None,
        derivations=derivations,
    )


def select_headline(changes: Mapping[MetricKey, MetricChange]) -> MetricChange | None:
    """The single change most worth surfacing, if any crossed the threshold.

    Ranked by absolute percentage movement. Ranking by size rather than by
    metric priority keeps the choice neutral: the app is not deciding that
    sleep matters more than heart rate, only that a 20% move is more
    conspicuous than a 12% one.
    """
    notable = [change for change in changes.values() if change.is_notable]
    if not notable:
        return None
    return max(notable, key=lambda change: change.magnitude)
