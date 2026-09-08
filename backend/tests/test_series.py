"""Tests for gap-aware daily series.

These cover the decision the rest of the app depends on: a missing day is a
gap, not a zero.
"""

from datetime import date

from app.domain.series import (
    Coverage,
    DailyPoint,
    DailySeries,
    build_series,
    date_range,
    series_from_values,
)

D = date(2026, 9, 1)


def test_date_range_is_inclusive():
    assert date_range(date(2026, 9, 1), date(2026, 9, 3)) == [
        date(2026, 9, 1),
        date(2026, 9, 2),
        date(2026, 9, 3),
    ]


def test_date_range_of_inverted_bounds_is_empty():
    assert date_range(date(2026, 9, 3), date(2026, 9, 1)) == []


def test_build_series_densifies_missing_days_as_gaps():
    observations = {date(2026, 9, 1): DailyPoint(day=date(2026, 9, 1), value=10.0)}
    series = build_series(date(2026, 9, 1), date(2026, 9, 3), observations)

    assert len(series) == 3
    assert [p.value for p in series.points] == [10.0, None, None]


def test_mean_ignores_gaps_rather_than_treating_them_as_zero():
    """The core correctness property: gaps must not drag the mean down."""
    series = series_from_values(
        date(2026, 9, 1),
        date(2026, 9, 4),
        [(date(2026, 9, 1), 10.0), (date(2026, 9, 4), 20.0)],
    )

    assert series.mean() == 15.0  # not 7.5, which zero-filling would produce


def test_mean_of_empty_series_is_none():
    series = series_from_values(date(2026, 9, 1), date(2026, 9, 3), [])
    assert series.mean() is None


def test_genuine_zero_is_kept_as_a_measurement():
    """A day with zero steps is data; a day with no record is not."""
    series = series_from_values(
        date(2026, 9, 1),
        date(2026, 9, 2),
        [(date(2026, 9, 1), 0.0), (date(2026, 9, 2), 100.0)],
    )

    assert series.coverage == Coverage(observed_days=2, expected_days=2)
    assert series.mean() == 50.0


def test_coverage_reports_observed_against_expected():
    series = series_from_values(
        date(2026, 9, 1),
        date(2026, 9, 10),
        [(date(2026, 9, day), 1.0) for day in (1, 2, 3, 4, 5, 6, 7)],
    )

    coverage = series.coverage
    assert coverage.observed_days == 7
    assert coverage.expected_days == 10
    assert coverage.ratio == 0.7
    assert coverage.is_complete is False


def test_coverage_ratio_of_empty_window_is_zero_not_an_error():
    assert Coverage(observed_days=0, expected_days=0).ratio == 0.0


def test_window_slices_inclusively():
    series = series_from_values(
        date(2026, 9, 1),
        date(2026, 9, 10),
        [(date(2026, 9, day), float(day)) for day in range(1, 11)],
    )

    window = series.window(date(2026, 9, 3), date(2026, 9, 5))
    assert [p.value for p in window.points] == [3.0, 4.0, 5.0]


def test_last_observed_day_ignores_trailing_gaps():
    """Anchoring the analysis window depends on this."""
    series = series_from_values(
        date(2026, 9, 1),
        date(2026, 9, 10),
        [(date(2026, 9, 1), 1.0), (date(2026, 9, 6), 6.0)],
    )

    assert series.last_observed_day == date(2026, 9, 6)


def test_last_observed_day_is_none_when_nothing_was_measured():
    series = series_from_values(date(2026, 9, 1), date(2026, 9, 3), [])
    assert series.last_observed_day is None


def test_derivation_counts_group_observed_days_by_source_field():
    series = DailySeries(
        (
            DailyPoint(day=date(2026, 9, 1), value=60.0, derivation="hr_resting"),
            DailyPoint(day=date(2026, 9, 2), value=61.0, derivation="hr_resting"),
            DailyPoint(day=date(2026, 9, 3), value=58.0, derivation="hr_lowest"),
            DailyPoint(day=date(2026, 9, 4)),
        )
    )

    assert series.derivation_counts() == {"hr_resting": 2, "hr_lowest": 1}
