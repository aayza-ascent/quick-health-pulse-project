"""Wording for the insights.

Health-adjacent phrasing is kept in one module rather than scattered across
components, so the language can be reviewed in a single place — and so a change
of mind about how careful to be is a change to one file.

Two rules govern everything here:

Describe, do not diagnose.
    'Sleep has decreased 18% compared with the previous 21-day baseline' is a
    statement about the data. 'Your sleep is poor' is a clinical claim this
    prototype has no basis for making.

Never imply a cause or an action.
    The app reports a change and shows its working. What that change means, and
    what to do about it, is not something a 10% threshold can answer.
"""

from collections.abc import Sequence

from app.domain.insights import ChangeDirection, InsufficientReason, MetricChange
from app.domain.metrics import MetricUnit

DISCLAIMER = "This prototype is for demonstration purposes and is not a medical diagnostic tool."

HEADLINE_TITLE = "Potential change worth reviewing"
NO_CHANGE_TITLE = "No notable changes"

NO_DATA_LABEL = "No data available for this day."

_INSUFFICIENT_WORDING = {
    InsufficientReason.NO_RECENT_DATA: (
        "No {metric} data was recorded in the last {recent_days} days, so there is "
        "nothing to compare."
    ),
    InsufficientReason.NO_BASELINE_DATA: (
        "There is no {metric} history before the last {recent_days} days, so no "
        "baseline can be established yet."
    ),
    InsufficientReason.LOW_RECENT_COVERAGE: (
        "{metric} was only recorded on {recent_observed} of the last {recent_days} "
        "days. That is too little to compare against the baseline."
    ),
    InsufficientReason.LOW_BASELINE_COVERAGE: (
        "{metric} was only recorded on {baseline_observed} of the {baseline_days} "
        "baseline days. That is too little to compare against."
    ),
    InsufficientReason.ZERO_BASELINE: (
        "The {metric} baseline is zero, so a percentage change cannot be calculated."
    ),
}


def describe_change(change: MetricChange) -> str:
    """One sentence stating what the data shows, and nothing more."""
    metric = change.metric.label
    baseline_days = change.baseline.coverage.expected_days
    recent_days = change.recent.coverage.expected_days

    if change.direction is ChangeDirection.INSUFFICIENT_DATA:
        reason = change.insufficient_reason or InsufficientReason.NO_RECENT_DATA
        return _INSUFFICIENT_WORDING[reason].format(
            metric=metric.lower(),
            recent_days=recent_days,
            baseline_days=baseline_days,
            recent_observed=change.recent.coverage.observed_days,
            baseline_observed=change.baseline.coverage.observed_days,
        )

    if change.direction is ChangeDirection.STABLE:
        return f"{metric} is stable compared with the previous {baseline_days}-day baseline."

    verb = "decreased" if change.direction is ChangeDirection.DECREASED else "increased"
    magnitude = round(change.magnitude)
    return (
        f"{metric} has {verb} {magnitude}% compared with the previous {baseline_days}-day baseline."
    )


def short_verdict(change: MetricChange) -> str:
    """A two-word summary for the metric card."""
    return {
        ChangeDirection.INCREASED: "Increased",
        ChangeDirection.DECREASED: "Decreased",
        ChangeDirection.STABLE: "Stable",
        ChangeDirection.INSUFFICIENT_DATA: "Not enough data",
    }[change.direction]


def unit_label(unit: MetricUnit) -> str:
    """How a metric's numbers should be described in prose."""
    return {
        MetricUnit.SECONDS: "hours and minutes",
        MetricUnit.BPM: "beats per minute",
        MetricUnit.STEPS: "steps",
    }[unit]


def describe_no_change(
    threshold_pct: float,
    baseline_days: int,
    uncomparable: Sequence[str] = (),
) -> str:
    """The headline when nothing crossed the threshold.

    The obvious wording — "every tracked metric is within 10% of its baseline" —
    is false whenever a metric could not be compared at all. Live sandbox data
    made that concrete: sleep and resting heart rate had too few recorded days
    to compare, so claiming they were within 10% asserted a comparison that
    never happened. Metrics that could not be assessed are named instead.
    """
    comparable = (
        f"No tracked metric moved more than {threshold_pct:g}% from its "
        f"{baseline_days}-day baseline."
    )
    if not uncomparable:
        return comparable

    names = _join_names(uncomparable)
    verb = "was" if len(uncomparable) == 1 else "were"
    return f"{comparable} {names} {verb} not compared: too few days recorded."


def _join_names(names: Sequence[str]) -> str:
    """ "A", "A and B", "A, B and C"."""
    items = list(names)
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} and {items[-1]}"
