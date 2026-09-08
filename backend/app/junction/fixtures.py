"""Deterministic local stand-in for Junction's sandbox.

Junction's synthetic connections are sandbox-only, expire after seven days, and
need credentials. This generator lets the app run, and the analysis be tested,
without any of that.

Two properties make it worth having rather than a hazard:

Same parsing path
    Payloads are emitted as plain dicts and validated through the same models as
    live responses, so a fixture cannot drift away from the real schema.

Deterministic
    A fixed seed means the same day produces the same numbers, so tests can
    assert on exact values and a reviewer sees the same screen described in the
    README.

The generated patient has a deliberate 7-day sleep decline, a mild resting
heart-rate rise, flat activity, and gaps — days with no measurement, and nights
where the provider recorded no resting heart rate. Those gaps exist to exercise
the missing-data handling rather than to flatter it.
"""

import random
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta

from app.junction.models import (
    ActivityResponse,
    ActivitySummary,
    SleepResponse,
    SleepSummary,
)
from app.junction.source import SourceDescriptor

DEFAULT_SEED = 20260908
DEFAULT_HISTORY_DAYS = 30


@dataclass(frozen=True)
class FixtureProfile:
    """The shape of the simulated patient's recent history.

    Values are chosen so the recent window differs from the baseline by enough
    to cross the reporting threshold on sleep and heart rate but not on
    activity, which exercises all three verdicts on one screen.
    """

    baseline_sleep_seconds: int = 27_300  # 7h 35m
    recent_sleep_seconds: int = 22_380  # 6h 13m
    baseline_resting_hr: float = 56.0
    recent_resting_hr: float = 61.0
    baseline_steps: int = 6_500
    recent_steps: int = 6_420

    # Days before "today" with no wearable data at all — the device was not worn
    # or did not sync. Placed in the baseline window so the recent window stays
    # fully covered while coverage reporting still has something to report.
    missing_day_offsets: tuple[int, ...] = (12, 19)

    # Nights the provider recorded without a resting heart rate, forcing the
    # metric resolution chain to fall back to another reading.
    nights_without_resting_hr: tuple[int, ...] = (3, 9, 17, 24)

    jitter: float = 0.06


@dataclass
class FixtureDataSource:
    """A :class:`~app.junction.source.HealthDataSource` backed by generated data."""

    provider: str = "fitbit"
    today: date = field(default_factory=lambda: datetime.now(UTC).date())
    history_days: int = DEFAULT_HISTORY_DAYS
    recent_days: int = 7
    seed: int = DEFAULT_SEED
    profile: FixtureProfile = field(default_factory=FixtureProfile)

    def describe(self) -> SourceDescriptor:
        return SourceDescriptor(provider=self.provider, mode="fixture")

    async def fetch_sleep(self, start: date, end: date) -> list[SleepSummary]:
        return [night for night in self._sleep() if start <= night.calendar_date <= end]

    async def fetch_activity(self, start: date, end: date) -> list[ActivitySummary]:
        return [day for day in self._activity() if start <= day.calendar_date <= end]

    # --- generation ----------------------------------------------------------

    def _days(self) -> list[tuple[int, date]]:
        """Offsets and dates, oldest first, excluding days with no data at all."""
        return [
            (offset, self.today - timedelta(days=offset))
            for offset in reversed(range(self.history_days))
            if offset not in self.profile.missing_day_offsets
        ]

    def _rng(self, salt: str) -> random.Random:
        """A generator seeded per metric, so adding one metric cannot shift another."""
        return random.Random(f"{self.seed}:{salt}")

    def _is_recent(self, offset: int) -> bool:
        return offset < self.recent_days

    def _jittered(self, rng: random.Random, value: float) -> float:
        spread = self.profile.jitter
        return value * (1 + rng.uniform(-spread, spread))

    def _sleep(self) -> list[SleepSummary]:
        rng = self._rng("sleep")
        hr_rng = self._rng("resting-hr")
        payload = []

        for offset, calendar_date in self._days():
            target = (
                self.profile.recent_sleep_seconds
                if self._is_recent(offset)
                else self.profile.baseline_sleep_seconds
            )
            asleep = int(self._jittered(rng, target))
            awake = int(asleep * rng.uniform(0.05, 0.12))

            resting_hr_target = (
                self.profile.recent_resting_hr
                if self._is_recent(offset)
                else self.profile.baseline_resting_hr
            )
            resting_hr = round(self._jittered(hr_rng, resting_hr_target))
            has_resting_hr = offset not in self.profile.nights_without_resting_hr

            # Bedtime the previous evening, waking on the calendar date.
            bedtime_start = datetime.combine(
                calendar_date - timedelta(days=1), time(23, 0), tzinfo=UTC
            ) + timedelta(minutes=rng.randint(-70, 70))

            payload.append(
                {
                    "id": f"fixture-sleep-{calendar_date.isoformat()}",
                    "calendar_date": calendar_date.isoformat(),
                    "bedtime_start": bedtime_start.isoformat(),
                    "bedtime_stop": (bedtime_start + timedelta(seconds=asleep + awake)).isoformat(),
                    "type": "long_sleep",
                    "duration": asleep + awake,
                    "total": asleep,
                    "awake": awake,
                    "deep": int(asleep * 0.20),
                    "rem": int(asleep * 0.22),
                    "light": asleep - int(asleep * 0.20) - int(asleep * 0.22),
                    "efficiency": round(asleep / (asleep + awake), 2),
                    "hr_resting": resting_hr if has_resting_hr else None,
                    "hr_lowest": resting_hr - rng.randint(1, 3),
                    "hr_average": resting_hr + rng.randint(3, 7),
                    "source": {"provider": self.provider, "type": "unknown"},
                }
            )

        return SleepResponse.model_validate({"sleep": payload}).sleep

    def _activity(self) -> list[ActivitySummary]:
        rng = self._rng("activity")
        payload = []

        for offset, calendar_date in self._days():
            target = (
                self.profile.recent_steps
                if self._is_recent(offset)
                else self.profile.baseline_steps
            )
            # Weekends look different from weekdays; a flat line would make the
            # "stable" verdict look like a stub rather than a finding.
            weekend_factor = 1.18 if calendar_date.weekday() >= 5 else 1.0
            steps = int(self._jittered(rng, target * weekend_factor))

            payload.append(
                {
                    "id": f"fixture-activity-{calendar_date.isoformat()}",
                    "calendar_date": calendar_date.isoformat(),
                    "steps": steps,
                    "distance": round(steps * 0.75, 1),
                    "calories_total": round(1_900 + steps * 0.045, 1),
                    "calories_active": round(steps * 0.045, 1),
                    "floors_climbed": rng.randint(2, 14),
                    "heart_rate": {
                        "avg_bpm": rng.randint(68, 78),
                        "min_bpm": rng.randint(48, 55),
                        "max_bpm": rng.randint(132, 158),
                    },
                    "source": {"provider": self.provider, "type": "unknown"},
                }
            )

        return ActivityResponse.model_validate({"activity": payload}).activity
