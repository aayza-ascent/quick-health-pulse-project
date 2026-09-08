"""Tests for the baseline comparison engine.

The engine is pure, so these tests state the product rules directly: where the
window sits, when a change is reported, and when the app declines to draw a
conclusion.
"""

from datetime import date, timedelta

import pytest

from app.domain.insights import (
    ChangeDirection,
    InsufficientReason,
    MetricKey,
    compare,
    resolve_anchor,
    resolve_windows,
    select_headline,
)
from app.domain.metrics import ACTIVITY, RESTING_HEART_RATE, SLEEP
from app.domain.series import series_from_values

ANCHOR = date(2026, 9, 8)
BASELINE_DAYS = 21
RECENT_DAYS = 7


def windows(anchor: date = ANCHOR):
    return resolve_windows(anchor, BASELINE_DAYS, RECENT_DAYS)


def flat_series(baseline_value: float | None, recent_value: float | None, anchor: date = ANCHOR):
    """A series that is constant across the baseline and constant across the recent window."""
    bounds = windows(anchor)
    values: list[tuple[date, float | None]] = []
    day = bounds.baseline_start
    while day <= bounds.recent_end:
        in_recent = day >= bounds.recent_start
        values.append((day, recent_value if in_recent else baseline_value))
        day += timedelta(days=1)
    return series_from_values(bounds.baseline_start, bounds.recent_end, values)


def run(series, metric=SLEEP, threshold_pct=10.0, min_coverage_ratio=0.7, anchor=ANCHOR):
    return compare(
        metric,
        series,
        windows(anchor),
        threshold_pct=threshold_pct,
        min_coverage_ratio=min_coverage_ratio,
    )


# --- window placement --------------------------------------------------------


def test_windows_are_adjacent_and_do_not_overlap():
    bounds = windows()

    assert bounds.recent_end == ANCHOR
    assert bounds.recent_start == ANCHOR - timedelta(days=6)
    assert bounds.baseline_end == bounds.recent_start - timedelta(days=1)
    assert bounds.baseline_start == bounds.baseline_end - timedelta(days=20)


def test_windows_span_exactly_baseline_plus_recent_days():
    bounds = windows()
    total = (bounds.end - bounds.start).days + 1

    assert total == BASELINE_DAYS + RECENT_DAYS == 28


def test_bounds_report_their_own_length():
    """Callers describing the window read it from the bounds, not from a metric."""
    bounds = windows()

    assert bounds.baseline_days == BASELINE_DAYS
    assert bounds.recent_days == RECENT_DAYS


def test_window_sizes_must_be_positive():
    with pytest.raises(ValueError, match="at least 1"):
        resolve_windows(ANCHOR, 0, 7)


def test_anchor_is_the_last_day_with_data_not_today():
    """A device that has not synced for two days must not read as a decline."""
    stale = series_from_values(
        ANCHOR - timedelta(days=10),
        ANCHOR,
        [(ANCHOR - timedelta(days=d), 100.0) for d in range(2, 11)],
    )

    assert resolve_anchor({MetricKey.SLEEP: stale}, fallback=ANCHOR) == ANCHOR - timedelta(days=2)


def test_anchor_falls_back_when_no_metric_has_data():
    empty = series_from_values(ANCHOR - timedelta(days=5), ANCHOR, [])
    assert resolve_anchor({MetricKey.SLEEP: empty}, fallback=ANCHOR) == ANCHOR


def test_anchor_uses_the_most_recent_day_across_all_metrics():
    sleep = series_from_values(
        ANCHOR - timedelta(days=5), ANCHOR, [(ANCHOR - timedelta(days=4), 1.0)]
    )
    activity = series_from_values(
        ANCHOR - timedelta(days=5), ANCHOR, [(ANCHOR - timedelta(days=1), 1.0)]
    )

    anchor = resolve_anchor({MetricKey.SLEEP: sleep, MetricKey.ACTIVITY: activity}, fallback=ANCHOR)
    assert anchor == ANCHOR - timedelta(days=1)


# --- the calculation ---------------------------------------------------------


def test_reports_the_percentage_change_between_window_means():
    change = run(flat_series(baseline_value=100.0, recent_value=82.0))

    assert change.baseline.mean == 100.0
    assert change.recent.mean == 82.0
    assert change.pct_change == pytest.approx(-18.0)
    assert change.absolute_change == pytest.approx(-18.0)
    assert change.direction is ChangeDirection.DECREASED


def test_worked_example_from_the_brief():
    """7h35m baseline against a 6h13m recent week reads as an 18% decrease."""
    baseline = 7 * 3600 + 35 * 60
    recent = 6 * 3600 + 13 * 60

    change = run(flat_series(baseline_value=baseline, recent_value=recent))

    assert change.direction is ChangeDirection.DECREASED
    assert round(change.pct_change or 0) == -18


def test_increase_beyond_threshold_is_reported_as_increased():
    change = run(flat_series(baseline_value=56.0, recent_value=61.0), metric=RESTING_HEART_RATE)

    assert change.pct_change == pytest.approx(8.928, abs=1e-3)
    assert change.direction is ChangeDirection.STABLE  # under the 10% threshold

    bigger = run(flat_series(baseline_value=56.0, recent_value=64.0), metric=RESTING_HEART_RATE)
    assert bigger.direction is ChangeDirection.INCREASED


@pytest.mark.parametrize(
    ("recent", "expected"),
    [
        (111.0, ChangeDirection.INCREASED),
        (110.0, ChangeDirection.STABLE),  # exactly at the threshold is not a change
        (100.0, ChangeDirection.STABLE),
        (90.0, ChangeDirection.STABLE),
        (89.0, ChangeDirection.DECREASED),
    ],
)
def test_threshold_boundaries_are_exclusive(recent: float, expected: ChangeDirection):
    change = run(flat_series(baseline_value=100.0, recent_value=recent))
    assert change.direction is expected


def test_threshold_is_configurable():
    series = flat_series(baseline_value=100.0, recent_value=95.0)

    assert run(series, threshold_pct=10.0).direction is ChangeDirection.STABLE
    assert run(series, threshold_pct=2.0).direction is ChangeDirection.DECREASED


def test_no_change_at_all_is_stable():
    change = run(flat_series(baseline_value=100.0, recent_value=100.0))

    assert change.pct_change == 0.0
    assert change.direction is ChangeDirection.STABLE
    assert change.is_notable is False


# --- missing data ------------------------------------------------------------


def test_gaps_do_not_manufacture_a_change():
    """The regression this project is most at risk of getting wrong.

    A recent window with two unworn nights, at the same nightly value as the
    baseline, must read as stable. Zero-filling the gaps would report a 29%
    decrease that never happened.
    """
    bounds = windows()
    values: list[tuple[date, float | None]] = []
    day = bounds.baseline_start
    while day <= bounds.recent_end:
        unworn = day in (bounds.recent_end, bounds.recent_end - timedelta(days=3))
        values.append((day, None if unworn else 100.0))
        day += timedelta(days=1)

    change = run(series_from_values(bounds.baseline_start, bounds.recent_end, values))

    assert change.direction is ChangeDirection.STABLE
    assert change.pct_change == pytest.approx(0.0)
    assert change.recent.coverage.observed_days == 5
    assert change.recent.coverage.expected_days == 7


def test_sparse_recent_window_is_reported_as_insufficient():
    bounds = windows()
    values: list[tuple[date, float | None]] = [
        (bounds.baseline_start + timedelta(days=i), 100.0) for i in range(BASELINE_DAYS)
    ]
    values.append((bounds.recent_start, 80.0))  # 1 of 7 days

    change = run(series_from_values(bounds.baseline_start, bounds.recent_end, values))

    assert change.direction is ChangeDirection.INSUFFICIENT_DATA
    assert change.insufficient_reason is InsufficientReason.LOW_RECENT_COVERAGE
    assert change.pct_change is None


def test_sparse_baseline_is_reported_as_insufficient():
    bounds = windows()
    values: list[tuple[date, float | None]] = [(bounds.baseline_start, 100.0)]
    values += [(bounds.recent_start + timedelta(days=i), 80.0) for i in range(RECENT_DAYS)]

    change = run(series_from_values(bounds.baseline_start, bounds.recent_end, values))

    assert change.insufficient_reason is InsufficientReason.LOW_BASELINE_COVERAGE


def test_no_recent_data_is_distinguished_from_sparse_data():
    change = run(flat_series(baseline_value=100.0, recent_value=None))

    assert change.insufficient_reason is InsufficientReason.NO_RECENT_DATA


def test_no_baseline_data_is_distinguished_from_sparse_data():
    change = run(flat_series(baseline_value=None, recent_value=100.0))

    assert change.insufficient_reason is InsufficientReason.NO_BASELINE_DATA


def test_zero_baseline_does_not_divide_by_zero():
    change = run(flat_series(baseline_value=0.0, recent_value=50.0))

    assert change.insufficient_reason is InsufficientReason.ZERO_BASELINE
    assert change.pct_change is None


def test_coverage_requirement_is_configurable():
    bounds = windows()
    values: list[tuple[date, float | None]] = [
        (bounds.baseline_start + timedelta(days=i), 100.0) for i in range(BASELINE_DAYS)
    ]
    values += [(bounds.recent_start + timedelta(days=i), 100.0) for i in range(3)]  # 3 of 7

    series = series_from_values(bounds.baseline_start, bounds.recent_end, values)

    assert run(series, min_coverage_ratio=0.7).direction is ChangeDirection.INSUFFICIENT_DATA
    assert run(series, min_coverage_ratio=0.4).direction is ChangeDirection.STABLE


def test_latest_value_comes_from_the_most_recent_observed_day():
    bounds = windows()
    values: list[tuple[date, float | None]] = [
        (bounds.baseline_start + timedelta(days=i), 100.0) for i in range(BASELINE_DAYS)
    ]
    values += [(bounds.recent_start + timedelta(days=i), 90.0 + i) for i in range(RECENT_DAYS - 1)]
    values.append((bounds.recent_end, None))  # today has not synced

    change = run(series_from_values(bounds.baseline_start, bounds.recent_end, values))

    assert change.latest_day == bounds.recent_end - timedelta(days=1)
    assert change.latest_value == 95.0


# --- headline selection ------------------------------------------------------


def test_headline_is_the_largest_movement():
    changes = {
        MetricKey.SLEEP: run(flat_series(100.0, 88.0), metric=SLEEP),
        MetricKey.RESTING_HEART_RATE: run(flat_series(60.0, 75.0), metric=RESTING_HEART_RATE),
        MetricKey.ACTIVITY: run(flat_series(6000.0, 6100.0), metric=ACTIVITY),
    }

    headline = select_headline(changes)

    assert headline is not None
    assert headline.metric is RESTING_HEART_RATE  # +25% beats -12%


def test_no_headline_when_everything_is_stable():
    changes = {MetricKey.SLEEP: run(flat_series(100.0, 101.0))}
    assert select_headline(changes) is None


def test_insufficient_data_is_never_promoted_to_a_headline():
    changes = {MetricKey.SLEEP: run(flat_series(baseline_value=None, recent_value=100.0))}
    assert select_headline(changes) is None
