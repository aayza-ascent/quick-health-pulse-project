"""Turning Junction summaries into one comparable number per day.

Each metric needs a rule for two awkward realities:

Provider variance
    Junction normalises across 300+ devices, but that does not mean every field
    is populated every night. Resting heart rate in particular is reported
    under three different fields depending on the device, so the metric is
    resolved through an explicit, ordered fallback chain and the field actually
    used is recorded per day.

Multiple records per day
    Junction returns a record per sleep *session*, not per night, so a day with
    a nap has two. Naps are excluded from sleep duration rather than silently
    inflating it — but what counts as a nap is decided by duration rather than
    by the provider's label, because the labels do not mean what they appear to.
    See EXPLICIT_NAP_TYPES.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from app.domain.series import DailyPoint, DailySeries, build_series
from app.junction.models import ActivitySummary, SleepSummary

# Only an explicit nap marker is trusted as meaning "nap".
#
# `short_sleep` is deliberately NOT in this set. It reads like a nap label, but
# Junction's Fitbit sandbox returns sessions of 6.5-8.5 hours under it, so
# treating it as a nap would exclude whole nights from the nightly total.
# https://docs.junction.com/api-reference/data/sleep/get-summary
EXPLICIT_NAP_TYPES = frozenset({"acknowledged_nap"})

# Below this, a session is treated as a nap whatever it is labelled. Duration is
# the more reliable signal: the meaning of the type field varies by provider,
# but three hours of sleep is not a night on anyone's definition.
NAP_MAX_SECONDS = 3 * 60 * 60


class MetricKey(StrEnum):
    SLEEP = "sleep"
    RESTING_HEART_RATE = "resting_heart_rate"
    ACTIVITY = "activity"


class MetricUnit(StrEnum):
    SECONDS = "seconds"
    BPM = "bpm"
    STEPS = "steps"


@dataclass(frozen=True)
class MetricDefinition:
    """What a metric is called and what its numbers mean.

    Deliberately carries no notion of a "good" or "bad" direction. This
    prototype reports that something moved, not whether that is desirable —
    that judgement belongs to a clinician, not to a threshold.
    """

    key: MetricKey
    label: str
    unit: MetricUnit
    description: str


SLEEP = MetricDefinition(
    key=MetricKey.SLEEP,
    label="Sleep",
    unit=MetricUnit.SECONDS,
    description="Total time asleep per night, excluding naps.",
)

RESTING_HEART_RATE = MetricDefinition(
    key=MetricKey.RESTING_HEART_RATE,
    label="Resting Heart Rate",
    unit=MetricUnit.BPM,
    description="Lowest sustained heart rate recorded overnight.",
)

ACTIVITY = MetricDefinition(
    key=MetricKey.ACTIVITY,
    label="Activity",
    unit=MetricUnit.STEPS,
    description="Steps recorded per day.",
)

ALL_METRICS: tuple[MetricDefinition, ...] = (SLEEP, RESTING_HEART_RATE, ACTIVITY)


# --- sleep -------------------------------------------------------------------


def _night_sleep_seconds(session: SleepSummary) -> tuple[float, str] | None:
    """Time asleep for one session, and the field it came from.

    ``total`` is time asleep and is the value we want. When a provider reports
    only time in bed, ``duration - awake`` reconstructs it. Falling back to
    ``duration`` alone slightly overstates sleep, so it is used last and
    labelled as such.
    """
    if session.total is not None:
        return float(session.total), "total"
    if session.duration is not None and session.awake is not None:
        return float(session.duration - session.awake), "duration - awake"
    if session.duration is not None:
        return float(session.duration), "duration (time in bed)"
    return None


def _is_nap(session: SleepSummary, seconds: float) -> bool:
    """Whether a session should be excluded from a night's sleep total."""
    if (session.sleep_type or "") in EXPLICIT_NAP_TYPES:
        return True
    return seconds < NAP_MAX_SECONDS


def sleep_series(start: date, end: date, sessions: Iterable[SleepSummary]) -> DailySeries:
    """Nightly sleep duration in seconds.

    Sessions on the same calendar date are summed, because fragmented sleep is
    still sleep. Naps are excluded unless they are all a day has, in which case
    they are used and labelled, since reporting nothing would misrepresent a
    day that does contain a measurement.
    """
    nights: dict[date, list[tuple[float, str]]] = {}
    naps: dict[date, list[tuple[float, str]]] = {}

    for session in sessions:
        resolved = _night_sleep_seconds(session)
        if resolved is None:
            continue
        bucket = naps if _is_nap(session, resolved[0]) else nights
        bucket.setdefault(session.calendar_date, []).append(resolved)

    observations: dict[date, DailyPoint] = {}
    for day in set(nights) | set(naps):
        entries = nights.get(day) or naps.get(day)
        if not entries:
            continue
        label = "total" if day in nights else "nap sessions only"
        derivations = {derivation for _, derivation in entries}
        # Surface the weaker derivation when a night needed reconstructing.
        if day in nights and derivations != {"total"}:
            label = ", ".join(sorted(derivations))
        observations[day] = DailyPoint(
            day=day,
            value=sum(value for value, _ in entries),
            derivation=label,
        )

    return build_series(start, end, observations)


# --- resting heart rate ------------------------------------------------------

# Ordered fallback chain. `hr_resting` is the metric we actually want;
# `hr_lowest` is the closest overnight proxy when a provider omits it;
# `hr_average` includes waking movement and so reads high, which is why it is
# last and always labelled.
SLEEP_HR_FIELDS: tuple[tuple[str, str], ...] = (
    ("hr_resting", "hr_resting"),
    ("hr_lowest", "hr_lowest"),
    ("hr_average", "hr_average"),
)


def _session_resting_hr(session: SleepSummary) -> tuple[float, str] | None:
    for attribute, label in SLEEP_HR_FIELDS:
        value = getattr(session, attribute)
        if value is not None:
            return float(value), label
    return None


def resting_heart_rate_series(
    start: date,
    end: date,
    sessions: Iterable[SleepSummary],
    activity: Iterable[ActivitySummary] = (),
) -> DailySeries:
    """Daily resting heart rate in bpm.

    Overnight readings are preferred because they are measured at rest. When a
    night is missing entirely, the daily activity rollup's ``resting_bpm`` is
    used instead — a genuine measurement for that day, just derived
    differently, so it is recorded under its own label rather than blended in
    silently.
    """
    observations: dict[date, DailyPoint] = {}

    for session in sessions:
        resolved = _session_resting_hr(session)
        if resolved is None:
            continue
        value, derivation = resolved
        existing = observations.get(session.calendar_date)
        # Multiple sessions in one night: keep the lowest reading, which is the
        # one closest to true resting.
        if existing is None or (existing.value is not None and value < existing.value):
            observations[session.calendar_date] = DailyPoint(
                day=session.calendar_date, value=value, derivation=derivation
            )

    for day in activity:
        if day.calendar_date in observations:
            continue
        if day.heart_rate and day.heart_rate.resting_bpm is not None:
            observations[day.calendar_date] = DailyPoint(
                day=day.calendar_date,
                value=float(day.heart_rate.resting_bpm),
                derivation="activity.heart_rate.resting_bpm",
            )

    return build_series(start, end, observations)


# --- activity ----------------------------------------------------------------


def activity_series(start: date, end: date, days: Iterable[ActivitySummary]) -> DailySeries:
    """Daily step count.

    A day the device recorded but on which the wearer genuinely did not move is
    a real zero, so zeros are kept. Only a day Junction returned no record for
    is treated as missing.
    """
    observations = {
        day.calendar_date: DailyPoint(
            day=day.calendar_date, value=float(day.steps), derivation="steps"
        )
        for day in days
        if day.steps is not None
    }
    return build_series(start, end, observations)


def build_all_series(
    start: date,
    end: date,
    sessions: Sequence[SleepSummary],
    activity: Sequence[ActivitySummary],
) -> dict[MetricKey, DailySeries]:
    """Every tracked metric as a gap-aware daily series over the same range."""
    return {
        MetricKey.SLEEP: sleep_series(start, end, sessions),
        MetricKey.RESTING_HEART_RATE: resting_heart_rate_series(start, end, sessions, activity),
        MetricKey.ACTIVITY: activity_series(start, end, activity),
    }
