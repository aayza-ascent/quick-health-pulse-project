"""Daily series with explicit gaps.

Wearable data is not a complete time series. Devices are taken off, batteries
die, syncs are delayed. The single most consequential decision in this project
is what to do about that.

Zero-filling a missing night would be wrong in a way that actively misleads:
a week containing two unworn nights would show a large sleep "decrease" that is
really an absence of measurement. So a day with no measurement is ``None``, and
every mean is taken over observed days only, with the coverage reported
alongside it so the reader can judge whether the mean is worth anything.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class DailyPoint:
    """One calendar day, which may or may not carry a measurement.

    ``derivation`` records which upstream field produced the value. Junction
    normalises across providers, but coverage still differs night to night, so
    the same metric can legitimately come from different fields on different
    days. Carrying that through to the evidence view is the difference between
    a number the reader can check and one they have to trust.
    """

    day: date
    value: float | None = None
    derivation: str | None = None

    @property
    def observed(self) -> bool:
        return self.value is not None


@dataclass(frozen=True)
class Coverage:
    """How much of a window was actually measured."""

    observed_days: int
    expected_days: int

    @property
    def ratio(self) -> float:
        if self.expected_days <= 0:
            return 0.0
        return self.observed_days / self.expected_days

    @property
    def is_complete(self) -> bool:
        return self.observed_days == self.expected_days


@dataclass(frozen=True)
class DailySeries:
    """A dense, gap-aware run of daily values ordered oldest to newest."""

    points: tuple[DailyPoint, ...]

    def __len__(self) -> int:
        return len(self.points)

    @property
    def observed_points(self) -> tuple[DailyPoint, ...]:
        return tuple(point for point in self.points if point.observed)

    @property
    def coverage(self) -> Coverage:
        return Coverage(observed_days=len(self.observed_points), expected_days=len(self.points))

    @property
    def last_observed_day(self) -> date | None:
        """The most recent day carrying a measurement, if any.

        Used to anchor the analysis window: comparing against a window ending
        today would drag in days the device has simply not synced yet.
        """
        observed = self.observed_points
        return observed[-1].day if observed else None

    def window(self, start: date, end: date) -> "DailySeries":
        """The sub-series covering ``[start, end]`` inclusive."""
        return DailySeries(tuple(p for p in self.points if start <= p.day <= end))

    def mean(self) -> float | None:
        """Mean over observed days only, or ``None`` if nothing was measured."""
        observed = self.observed_points
        if not observed:
            return None
        # value is not None for observed points; the guard keeps mypy honest.
        return sum(p.value for p in observed if p.value is not None) / len(observed)

    def derivation_counts(self) -> dict[str, int]:
        """How many observed days came from each upstream field."""
        counts: dict[str, int] = {}
        for point in self.observed_points:
            if point.derivation:
                counts[point.derivation] = counts.get(point.derivation, 0) + 1
        return counts


def date_range(start: date, end: date) -> list[date]:
    """Every date in ``[start, end]`` inclusive, ascending."""
    if end < start:
        return []
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def build_series(
    start: date,
    end: date,
    observations: Mapping[date, DailyPoint],
) -> DailySeries:
    """Lay observations onto a complete calendar, leaving gaps as gaps.

    Densifying here rather than at each call site means downstream code can
    assume one point per day and never has to guess whether a missing key means
    "no data" or "not looked up".
    """
    return DailySeries(
        tuple(observations.get(day, DailyPoint(day=day)) for day in date_range(start, end))
    )


def series_from_values(
    start: date, end: date, values: Iterable[tuple[date, float | None]]
) -> DailySeries:
    """Convenience builder for tests and simple call sites."""
    observations = {
        day: DailyPoint(day=day, value=value) for day, value in values if value is not None
    }
    return build_series(start, end, observations)
