"""Tests for metric extraction.

These pin down the provider-variance rules: which field a metric falls back to
when the preferred one is absent, and how multiple records for one day are
reconciled.
"""

from datetime import date

from app.domain.metrics import (
    activity_series,
    build_all_series,
    resting_heart_rate_series,
    sleep_series,
)
from app.junction.models import ActivitySummary, SleepSummary

DAY = date(2026, 9, 1)
NEXT = date(2026, 9, 2)


def sleep(day: date = DAY, **fields: object) -> SleepSummary:
    return SleepSummary.model_validate({"calendar_date": day.isoformat(), **fields})


def activity(day: date = DAY, **fields: object) -> ActivitySummary:
    return ActivitySummary.model_validate({"calendar_date": day.isoformat(), **fields})


# --- sleep duration ----------------------------------------------------------


def test_sleep_prefers_total_time_asleep():
    series = sleep_series(DAY, DAY, [sleep(total=25_200, duration=28_800, awake=3_600)])
    point = series.points[0]

    assert point.value == 25_200
    assert point.derivation == "total"


def test_sleep_reconstructs_from_time_in_bed_minus_awake():
    """Some providers report time in bed but no explicit asleep total."""
    series = sleep_series(DAY, DAY, [sleep(duration=28_800, awake=3_600)])
    point = series.points[0]

    assert point.value == 25_200
    assert point.derivation == "duration - awake"


def test_sleep_falls_back_to_time_in_bed_and_says_so():
    """The weakest derivation overstates sleep, so it must be labelled."""
    series = sleep_series(DAY, DAY, [sleep(duration=28_800)])
    point = series.points[0]

    assert point.value == 28_800
    assert point.derivation == "duration (time in bed)"


def test_sleep_with_no_usable_duration_is_a_gap():
    series = sleep_series(DAY, DAY, [sleep(score=80)])
    assert series.points[0].observed is False


def test_fragmented_sessions_on_one_night_are_summed():
    series = sleep_series(DAY, DAY, [sleep(total=14_400), sleep(total=10_800)])
    assert series.points[0].value == 25_200


def test_naps_are_excluded_when_a_real_night_exists():
    series = sleep_series(
        DAY,
        DAY,
        [sleep(total=25_200, type="long_sleep"), sleep(total=3_600, type="acknowledged_nap")],
    )

    assert series.points[0].value == 25_200


def test_short_sleep_label_is_not_treated_as_a_nap():
    """Regression from live Junction data.

    Junction's Fitbit sandbox returns sessions of 6.5-8.5 hours labelled
    `short_sleep`. Those are nights, and excluding them as naps would drop real
    sleep from the nightly total.
    """
    series = sleep_series(DAY, DAY, [sleep(total=30_420, type="short_sleep")])
    point = series.points[0]

    assert point.value == 30_420
    assert point.derivation == "total", "an 8h session must not be labelled a nap"


def test_a_night_with_both_long_and_short_sleep_records_sums_both():
    """The case the old label-based rule would have silently under-reported."""
    series = sleep_series(
        DAY,
        DAY,
        [sleep(total=18_000, type="long_sleep"), sleep(total=10_800, type="short_sleep")],
    )

    assert series.points[0].value == 28_800


def test_a_genuinely_short_session_is_treated_as_a_nap_whatever_its_label():
    """Duration is the more reliable signal, since label meaning varies by provider."""
    series = sleep_series(DAY, DAY, [sleep(total=2_400, type="long_sleep")])

    assert series.points[0].derivation == "nap sessions only"


def test_a_short_session_is_excluded_when_a_real_night_exists():
    series = sleep_series(
        DAY,
        DAY,
        [sleep(total=27_000, type="long_sleep"), sleep(total=1_800, type="unknown")],
    )

    assert series.points[0].value == 27_000


def test_a_day_of_only_naps_is_reported_and_labelled():
    """Reporting nothing would misrepresent a day that does contain data."""
    series = sleep_series(DAY, DAY, [sleep(total=3_600, type="acknowledged_nap")])
    point = series.points[0]

    assert point.value == 3_600
    assert point.derivation == "nap sessions only"


def test_sleep_series_spans_the_requested_range_with_gaps():
    series = sleep_series(DAY, date(2026, 9, 4), [sleep(day=NEXT, total=25_200)])

    assert len(series) == 4
    assert [p.observed for p in series.points] == [False, True, False, False]


# --- resting heart rate ------------------------------------------------------


def test_resting_hr_prefers_the_dedicated_field():
    series = resting_heart_rate_series(
        DAY, DAY, [sleep(hr_resting=58, hr_lowest=54, hr_average=66)]
    )
    point = series.points[0]

    assert point.value == 58
    assert point.derivation == "hr_resting"


def test_resting_hr_falls_back_to_lowest_overnight_reading():
    series = resting_heart_rate_series(DAY, DAY, [sleep(hr_lowest=54, hr_average=66)])
    point = series.points[0]

    assert point.value == 54
    assert point.derivation == "hr_lowest"


def test_resting_hr_falls_back_last_to_the_overnight_average():
    """Includes waking movement, so it reads high and is labelled accordingly."""
    series = resting_heart_rate_series(DAY, DAY, [sleep(hr_average=66)])
    point = series.points[0]

    assert point.value == 66
    assert point.derivation == "hr_average"


def test_resting_hr_uses_activity_rollup_when_the_night_is_missing():
    series = resting_heart_rate_series(
        DAY,
        DAY,
        [],
        [activity(heart_rate={"resting_bpm": 61})],
    )
    point = series.points[0]

    assert point.value == 61
    assert point.derivation == "activity.heart_rate.resting_bpm"


def test_overnight_reading_wins_over_the_activity_rollup():
    series = resting_heart_rate_series(
        DAY,
        DAY,
        [sleep(hr_resting=58)],
        [activity(heart_rate={"resting_bpm": 61})],
    )

    assert series.points[0].derivation == "hr_resting"


def test_lowest_reading_wins_when_a_night_has_several_sessions():
    series = resting_heart_rate_series(DAY, DAY, [sleep(hr_resting=62), sleep(hr_resting=57)])
    assert series.points[0].value == 57


def test_night_with_no_heart_rate_at_all_is_a_gap():
    series = resting_heart_rate_series(DAY, DAY, [sleep(total=25_200)])
    assert series.points[0].observed is False


def test_derivations_are_counted_across_a_mixed_range():
    """This is what the evidence view reports when coverage was uneven."""
    series = resting_heart_rate_series(
        DAY,
        date(2026, 9, 3),
        [
            sleep(day=DAY, hr_resting=58),
            sleep(day=NEXT, hr_lowest=54),
            sleep(day=date(2026, 9, 3), hr_resting=59),
        ],
    )

    assert series.derivation_counts() == {"hr_resting": 2, "hr_lowest": 1}


# --- activity ----------------------------------------------------------------


def test_activity_reads_steps():
    series = activity_series(DAY, DAY, [activity(steps=6_421)])
    assert series.points[0].value == 6_421


def test_a_recorded_zero_step_day_is_data_not_a_gap():
    series = activity_series(DAY, DAY, [activity(steps=0)])
    point = series.points[0]

    assert point.observed is True
    assert point.value == 0.0


def test_a_day_with_no_step_field_is_a_gap():
    series = activity_series(DAY, DAY, [activity(calories_total=2_000)])
    assert series.points[0].observed is False


# --- assembly ----------------------------------------------------------------


def test_build_all_series_covers_every_metric_over_one_range():
    result = build_all_series(
        DAY,
        NEXT,
        [sleep(total=25_200, hr_resting=58)],
        [activity(steps=6_421)],
    )

    assert set(result) == {"sleep", "resting_heart_rate", "activity"}
    assert all(len(series) == 2 for series in result.values())
