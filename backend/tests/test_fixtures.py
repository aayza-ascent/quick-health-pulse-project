"""Tests for the fixture generator.

The generator underpins both the tests and the runnable demo, so it needs to be
trustworthy in its own right: deterministic, correctly shaped, and honest about
the gaps it claims to contain.
"""

from datetime import date, timedelta

from app.junction.fixtures import FixtureDataSource, FixtureProfile

TODAY = date(2026, 9, 8)


def make_source(**overrides: object) -> FixtureDataSource:
    return FixtureDataSource(today=TODAY, **overrides)  # type: ignore[arg-type]


async def test_generates_requested_history_minus_gaps():
    source = make_source()
    nights = await source.fetch_sleep(TODAY - timedelta(days=29), TODAY)

    expected = 30 - len(FixtureProfile().missing_day_offsets)
    assert len(nights) == expected


async def test_is_deterministic_across_instances():
    first = await make_source().fetch_sleep(TODAY - timedelta(days=29), TODAY)
    second = await make_source().fetch_sleep(TODAY - timedelta(days=29), TODAY)

    assert [n.total for n in first] == [n.total for n in second]


async def test_different_seeds_produce_different_data():
    a = await make_source(seed=1).fetch_sleep(TODAY - timedelta(days=29), TODAY)
    b = await make_source(seed=2).fetch_sleep(TODAY - timedelta(days=29), TODAY)

    assert [n.total for n in a] != [n.total for n in b]


async def test_missing_days_are_absent_rather_than_zeroed():
    source = make_source()
    nights = await source.fetch_sleep(TODAY - timedelta(days=29), TODAY)
    present = {night.calendar_date for night in nights}

    for offset in FixtureProfile().missing_day_offsets:
        assert TODAY - timedelta(days=offset) not in present

    # Nothing that is present is a zero masquerading as a measurement.
    assert all(night.total and night.total > 0 for night in nights)


async def test_some_nights_have_no_resting_heart_rate():
    """Exercises the metric fallback chain rather than assuming full coverage."""
    source = make_source()
    nights = await source.fetch_sleep(TODAY - timedelta(days=29), TODAY)

    without = [n for n in nights if n.hr_resting is None]
    assert without, "expected at least one night lacking a resting heart rate"
    assert all(n.hr_lowest is not None for n in without), "fallback reading must exist"


async def test_recent_window_sleeps_less_than_baseline():
    source = make_source()
    nights = await source.fetch_sleep(TODAY - timedelta(days=27), TODAY)
    by_date = {n.calendar_date: n for n in nights}

    recent = [
        by_date[TODAY - timedelta(days=o)].total
        for o in range(7)
        if TODAY - timedelta(days=o) in by_date
    ]
    baseline = [
        by_date[TODAY - timedelta(days=o)].total
        for o in range(7, 28)
        if TODAY - timedelta(days=o) in by_date
    ]

    assert all(v is not None for v in recent + baseline)
    recent_mean = sum(v for v in recent if v) / len(recent)
    baseline_mean = sum(v for v in baseline if v) / len(baseline)
    assert recent_mean < baseline_mean


async def test_date_range_is_respected():
    source = make_source()
    start, end = TODAY - timedelta(days=5), TODAY - timedelta(days=2)
    nights = await source.fetch_sleep(start, end)

    assert nights
    assert all(start <= n.calendar_date <= end for n in nights)


async def test_activity_carries_steps_and_attribution():
    source = make_source(provider="oura")
    days = await source.fetch_activity(TODAY - timedelta(days=6), TODAY)

    assert all(day.steps and day.steps > 0 for day in days)
    assert all(day.source and day.source.provider == "oura" for day in days)


def test_descriptor_is_explicit_about_being_simulated():
    """The UI must never present generated data as if it came from a device."""
    descriptor = make_source().describe()

    assert descriptor.is_live is False
    assert descriptor.label == "Simulated Fitbit data"
