"""Tests for the orchestration layer.

Mostly about the concurrent fetch: it is the kind of property that is easy to
undo in a later refactor without any test noticing, so the overlap is asserted
directly rather than inferred from a stopwatch.
"""

import asyncio
from datetime import date

import pytest

from app.config import Settings
from app.errors import JunctionRateLimitError
from app.junction.models import ActivitySummary, SleepSummary
from app.junction.source import SourceDescriptor
from app.services.pulse import PulseService

TODAY = date(2026, 9, 9)


class RecordingSource:
    """Records when each fetch starts and finishes, so overlap is observable."""

    def __init__(self, fail_on: str | None = None) -> None:
        self.events: list[str] = []
        self._fail_on = fail_on

    def describe(self) -> SourceDescriptor:
        return SourceDescriptor(provider="fitbit", mode="junction")

    async def _run(self, name: str) -> None:
        self.events.append(f"{name}:start")
        # Yield to the event loop, which is where a sequential implementation
        # would let the other fetch run to completion first.
        await asyncio.sleep(0)
        if self._fail_on == name:
            self.events.append(f"{name}:fail")
            raise JunctionRateLimitError()
        self.events.append(f"{name}:end")

    async def fetch_sleep(self, start: date, end: date) -> list[SleepSummary]:
        await self._run("sleep")
        return []

    async def fetch_activity(self, start: date, end: date) -> list[ActivitySummary]:
        await self._run("activity")
        return []


def settings() -> Settings:
    return Settings(_env_file=None)  # type: ignore[call-arg]


async def test_the_two_summary_fetches_overlap():
    """Sequential awaits cost the sum of both round trips instead of the longer.

    Against the EU sandbox that was roughly 240ms rather than 135ms.
    """
    source = RecordingSource()

    await PulseService(source, settings()).build(today=TODAY)

    assert source.events.index("activity:start") < source.events.index("sleep:end"), (
        f"expected the fetches to overlap, got {source.events}"
    )


async def test_a_failing_fetch_keeps_its_own_exception_type():
    """The API layer maps on exception type, so gather must not wrap it."""
    source = RecordingSource(fail_on="sleep")

    with pytest.raises(JunctionRateLimitError):
        await PulseService(source, settings()).build(today=TODAY)


async def test_the_sibling_fetch_still_settles_when_one_fails():
    """Otherwise a request is left in flight to fail as the client closes."""
    source = RecordingSource(fail_on="sleep")

    with pytest.raises(JunctionRateLimitError):
        await PulseService(source, settings()).build(today=TODAY)

    assert "activity:end" in source.events, source.events


async def test_the_window_is_reported_alongside_the_threshold_used():
    source = RecordingSource()

    pulse = await PulseService(source, settings()).build(today=TODAY)

    assert pulse.threshold_pct == 10.0
    assert pulse.bounds.baseline_days == 21
    assert pulse.bounds.recent_days == 7
