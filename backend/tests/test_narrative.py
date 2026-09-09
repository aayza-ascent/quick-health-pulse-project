"""Tests for insight wording.

The assertions here are as much about what the app must *not* say as what it
says: no diagnosis, no cause, no recommendation.
"""

from datetime import date, timedelta

import pytest

from app.domain.insights import (
    ChangeDirection,
    InsufficientReason,
    MetricChange,
    WindowSummary,
    compare,
    resolve_windows,
)
from app.domain.metrics import ACTIVITY, RESTING_HEART_RATE, SLEEP, MetricDefinition
from app.domain.narrative import (
    DISCLAIMER,
    describe_change,
    describe_no_change,
    short_verdict,
)
from app.domain.series import Coverage, series_from_values

ANCHOR = date(2026, 9, 8)


def change_for(
    baseline: float | None, recent: float | None, metric: MetricDefinition = SLEEP
) -> MetricChange:
    bounds = resolve_windows(ANCHOR, 21, 7)
    values: list[tuple[date, float | None]] = []
    day = bounds.baseline_start
    while day <= bounds.recent_end:
        values.append((day, recent if day >= bounds.recent_start else baseline))
        day += timedelta(days=1)
    series = series_from_values(bounds.baseline_start, bounds.recent_end, values)
    return compare(metric, series, bounds, threshold_pct=10.0, min_coverage_ratio=0.7)


def test_decrease_is_described_with_its_baseline():
    sentence = describe_change(change_for(100.0, 82.0))
    assert sentence == "Sleep has decreased 18% compared with the previous 21-day baseline."


def test_increase_is_described_symmetrically():
    sentence = describe_change(change_for(60.0, 75.0, metric=RESTING_HEART_RATE))
    assert sentence == (
        "Resting Heart Rate has increased 25% compared with the previous 21-day baseline."
    )


def test_stable_metric_says_so_plainly():
    sentence = describe_change(change_for(6000.0, 6100.0, metric=ACTIVITY))
    assert sentence == "Activity is stable compared with the previous 21-day baseline."


def test_insufficient_coverage_explains_which_days_are_missing():
    bounds = resolve_windows(ANCHOR, 21, 7)
    values: list[tuple[date, float | None]] = [
        (bounds.baseline_start + timedelta(days=i), 100.0) for i in range(21)
    ]
    values.append((bounds.recent_start, 80.0))
    series = series_from_values(bounds.baseline_start, bounds.recent_end, values)
    change = compare(SLEEP, series, bounds, threshold_pct=10.0, min_coverage_ratio=0.7)

    sentence = describe_change(change)
    assert "only recorded on 1 of the last 7 days" in sentence
    assert "too little to compare" in sentence


@pytest.mark.parametrize("reason", list(InsufficientReason))
def test_every_insufficient_reason_has_wording(reason: InsufficientReason):
    """A missing branch would surface as a KeyError in front of the user."""
    baseline = WindowSummary(
        label="Previous 21-day average",
        start=ANCHOR - timedelta(days=27),
        end=ANCHOR - timedelta(days=7),
        mean=None,
        coverage=Coverage(observed_days=2, expected_days=21),
    )
    recent = WindowSummary(
        label="Recent 7-day average",
        start=ANCHOR - timedelta(days=6),
        end=ANCHOR,
        mean=None,
        coverage=Coverage(observed_days=1, expected_days=7),
    )
    change = MetricChange(
        metric=SLEEP,
        direction=ChangeDirection.INSUFFICIENT_DATA,
        baseline=baseline,
        recent=recent,
        threshold_pct=10.0,
        insufficient_reason=reason,
    )

    assert describe_change(change)


@pytest.mark.parametrize(
    "baseline,recent,expected",
    [
        (100.0, 82.0, "Decreased"),
        (100.0, 130.0, "Increased"),
        (100.0, 100.0, "Stable"),
        (None, 100.0, "Not enough data"),
    ],
)
def test_short_verdicts(baseline, recent, expected):
    assert short_verdict(change_for(baseline, recent)) == expected


def test_wording_makes_no_clinical_claim():
    """Guards against the phrasing drifting toward diagnosis or advice."""
    forbidden = (
        "you should",
        "we recommend",
        "consult",
        "risk",
        "diagnos",
        "abnormal",
        "unhealthy",
        "poor",
        "concerning",
        "symptom",
        "treat",
        "condition",
    )
    sentences = [
        describe_change(change_for(100.0, 82.0)),
        describe_change(change_for(60.0, 75.0, metric=RESTING_HEART_RATE)),
        describe_change(change_for(6000.0, 6100.0, metric=ACTIVITY)),
        describe_change(change_for(None, 100.0)),
    ]

    for sentence in sentences:
        lowered = sentence.lower()
        for term in forbidden:
            assert term not in lowered, f"{term!r} appeared in: {sentence}"


def test_disclaimer_is_explicit_about_not_being_diagnostic():
    assert "not a medical diagnostic tool" in DISCLAIMER


class TestNoChangeWording:
    """The no-change headline must not assert comparisons that never happened.

    Live sandbox data made this concrete: sleep and resting heart rate had too
    few recorded days to compare, so "every tracked metric is within 10% of its
    baseline" was simply false.
    """

    def test_states_the_threshold_when_everything_was_comparable(self):
        assert describe_no_change(10.0, 21) == (
            "No tracked metric moved more than 10% from its 21-day baseline."
        )

    def test_names_a_single_metric_that_could_not_be_compared(self):
        body = describe_no_change(10.0, 21, ["Sleep"])

        assert body.endswith("Sleep was not compared: too few days recorded.")
        assert "every" not in body.lower()

    def test_names_two_metrics_with_a_conjunction(self):
        body = describe_no_change(10.0, 21, ["Sleep", "Resting Heart Rate"])

        assert "Sleep and Resting Heart Rate were not compared" in body

    def test_names_three_metrics_as_a_list(self):
        body = describe_no_change(10.0, 21, ["Sleep", "Resting Heart Rate", "Activity"])

        assert "Sleep, Resting Heart Rate and Activity were not compared" in body

    def test_never_claims_an_uncompared_metric_was_within_the_threshold(self):
        """The specific overclaim this function exists to prevent."""
        body = describe_no_change(10.0, 21, ["Sleep", "Resting Heart Rate"]).lower()

        assert "every tracked metric is within" not in body
