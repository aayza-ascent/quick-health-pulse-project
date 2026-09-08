"""Tests for the Junction HTTP client.

The sleep payload below is Junction's own documented example response, copied
verbatim from the API reference. Parsing it is the check that the models in
app.junction.models actually bind to the published schema — worth having when
the sandbox is not reachable from CI.

https://docs.junction.com/api-reference/data/sleep/get-summary
"""

import json
from datetime import date

import httpx
import pytest
import respx

from app.errors import (
    JunctionAuthError,
    JunctionError,
    JunctionNotFoundError,
    JunctionRateLimitError,
    JunctionUnavailableError,
)
from app.junction.client import JunctionClient

BASE_URL = "https://api.sandbox.us.junction.com"
USER_ID = "1449752e-0d8a-40e0-9206-91ab099b2537"

DOCUMENTED_SLEEP_RESPONSE = {
    "sleep": [
        {
            "average_hrv": 78,
            "awake": 2400,
            "bedtime_start": "2023-02-27T12:31:24+00:00",
            "bedtime_stop": "2023-02-27T12:31:24+00:00",
            "calendar_date": "2023-02-27",
            "created_at": "2023-02-27T20:31:24+00:00",
            "date": "2023-02-27T12:31:24+00:00",
            "deep": 2400,
            "duration": 28800,
            "efficiency": 0.97,
            "hr_average": 50,
            "hr_lowest": 43,
            "id": "e2e0eb04-6641-4858-9de5-649efb41b346",
            "latency": 1000,
            "light": 2400,
            "recovery_readiness_score": 82,
            "rem": 2400,
            "respiratory_rate": 14,
            "skin_temperature": 36.5,
            "source": {
                "device_id": "550e8400-e29b-41d4-a716-446655440000",
                "provider": "oura",
                "type": "unknown",
            },
            "temperature_delta": -0.2,
            "timezone_offset": 2400,
            "total": 28800,
            "updated_at": "2023-02-28T01:22:38+00:00",
            "user_id": USER_ID,
        }
    ]
}

DOCUMENTED_ACTIVITY_RESPONSE = {
    "activity": [
        {
            "id": "b0f0d6a7-3ba0-4a1e-9c0c-4d2ba4a1b111",
            "user_id": USER_ID,
            "calendar_date": "2023-02-27",
            "steps": 6421,
            "calories_total": 2310.5,
            "calories_active": 620.0,
            "distance": 4821.0,
            "floors_climbed": 8,
            "heart_rate": {"avg_bpm": 72, "min_bpm": 51, "max_bpm": 148, "resting_bpm": 61},
            "source": {"provider": "fitbit", "type": "unknown"},
            "created_at": "2023-02-27T20:31:24+00:00",
            "updated_at": "2023-02-28T01:22:38+00:00",
        }
    ]
}


def make_client(**overrides: object) -> JunctionClient:
    kwargs: dict[str, object] = {
        "api_key": "test-key",
        "user_id": USER_ID,
        "base_url": BASE_URL,
        "provider": "fitbit",
        "max_retries": 2,
    }
    kwargs.update(overrides)
    return JunctionClient(**kwargs)  # type: ignore[arg-type]


@respx.mock
async def test_fetch_sleep_parses_documented_payload():
    route = respx.get(f"{BASE_URL}/v2/summary/sleep/{USER_ID}").mock(
        return_value=httpx.Response(200, json=DOCUMENTED_SLEEP_RESPONSE)
    )

    async with make_client() as client:
        sessions = await client.fetch_sleep(date(2023, 2, 20), date(2023, 2, 27))

    assert len(sessions) == 1
    night = sessions[0]
    assert night.calendar_date == date(2023, 2, 27)
    assert night.total == 28800
    assert night.hr_lowest == 43
    assert night.hr_resting is None  # absent from the payload, not zero
    assert night.source is not None
    assert night.source.provider == "oura"

    # The date range is passed through as Junction documents it.
    assert route.calls.last.request.url.params["start_date"] == "2023-02-20"
    assert route.calls.last.request.url.params["end_date"] == "2023-02-27"


@respx.mock
async def test_fetch_activity_parses_nested_heart_rate():
    respx.get(f"{BASE_URL}/v2/summary/activity/{USER_ID}").mock(
        return_value=httpx.Response(200, json=DOCUMENTED_ACTIVITY_RESPONSE)
    )

    async with make_client() as client:
        days = await client.fetch_activity(date(2023, 2, 20), date(2023, 2, 27))

    assert days[0].steps == 6421
    assert days[0].heart_rate is not None
    assert days[0].heart_rate.resting_bpm == 61


@respx.mock
async def test_api_key_is_sent_and_never_echoed():
    route = respx.get(f"{BASE_URL}/v2/summary/sleep/{USER_ID}").mock(
        return_value=httpx.Response(200, json={"sleep": []})
    )

    async with make_client(api_key="secret-key") as client:
        await client.fetch_sleep(date(2023, 2, 20), date(2023, 2, 27))

    assert route.calls.last.request.headers["x-vital-api-key"] == "secret-key"


@respx.mock
async def test_unknown_fields_do_not_break_parsing():
    """A provider gaining a field must not take the service down."""
    payload = {
        "sleep": [{"calendar_date": "2024-05-01", "total": 1000, "brand_new_field": {"a": 1}}],
        "unexpected_envelope_key": True,
    }
    respx.get(f"{BASE_URL}/v2/summary/sleep/{USER_ID}").mock(
        return_value=httpx.Response(200, json=payload)
    )

    async with make_client() as client:
        sessions = await client.fetch_sleep(date(2024, 5, 1), date(2024, 5, 1))

    assert sessions[0].total == 1000


@respx.mock
async def test_retries_transient_failure_then_succeeds():
    respx.get(f"{BASE_URL}/v2/summary/sleep/{USER_ID}").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(200, json=DOCUMENTED_SLEEP_RESPONSE),
        ]
    )

    async with make_client() as client:
        sessions = await client.fetch_sleep(date(2023, 2, 20), date(2023, 2, 27))

    assert len(sessions) == 1


@respx.mock
async def test_gives_up_after_max_retries():
    route = respx.get(f"{BASE_URL}/v2/summary/sleep/{USER_ID}").mock(
        return_value=httpx.Response(503)
    )

    async with make_client(max_retries=2) as client:
        with pytest.raises(JunctionUnavailableError):
            await client.fetch_sleep(date(2023, 2, 20), date(2023, 2, 27))

    assert route.call_count == 3  # initial attempt plus two retries


@respx.mock
async def test_client_errors_are_not_retried():
    """A 400 is our bug; retrying it only wastes the user's time."""
    route = respx.get(f"{BASE_URL}/v2/summary/sleep/{USER_ID}").mock(
        return_value=httpx.Response(400)
    )

    async with make_client() as client:
        with pytest.raises(JunctionError):
            await client.fetch_sleep(date(2023, 2, 20), date(2023, 2, 27))

    assert route.call_count == 1


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, JunctionAuthError),
        (403, JunctionAuthError),
        (404, JunctionNotFoundError),
    ],
)
@respx.mock
async def test_status_codes_map_to_domain_errors(status: int, expected: type[Exception]):
    respx.get(f"{BASE_URL}/v2/summary/sleep/{USER_ID}").mock(return_value=httpx.Response(status))

    async with make_client() as client:
        with pytest.raises(expected):
            await client.fetch_sleep(date(2023, 2, 20), date(2023, 2, 27))


@respx.mock
async def test_rate_limit_is_reported_distinctly():
    respx.get(f"{BASE_URL}/v2/summary/sleep/{USER_ID}").mock(return_value=httpx.Response(429))

    async with make_client(max_retries=0) as client:
        with pytest.raises(JunctionRateLimitError):
            await client.fetch_sleep(date(2023, 2, 20), date(2023, 2, 27))


@respx.mock
async def test_transport_error_becomes_unavailable():
    respx.get(f"{BASE_URL}/v2/summary/sleep/{USER_ID}").mock(
        side_effect=httpx.ConnectError("no route to host")
    )

    async with make_client(max_retries=0) as client:
        with pytest.raises(JunctionUnavailableError):
            await client.fetch_sleep(date(2023, 2, 20), date(2023, 2, 27))


@respx.mock
async def test_malformed_payload_becomes_domain_error():
    respx.get(f"{BASE_URL}/v2/summary/sleep/{USER_ID}").mock(
        return_value=httpx.Response(200, json={"sleep": [{"calendar_date": "not-a-date"}]})
    )

    async with make_client() as client:
        with pytest.raises(JunctionError):
            await client.fetch_sleep(date(2023, 2, 20), date(2023, 2, 27))


@respx.mock
async def test_provisioning_creates_user_and_demo_connection():
    respx.post(f"{BASE_URL}/v2/user/").mock(
        return_value=httpx.Response(200, json={"user_id": USER_ID, "client_user_id": "demo"})
    )
    connect = respx.post(f"{BASE_URL}/v2/link/connect/demo").mock(
        return_value=httpx.Response(
            200, json={"success": True, "detail": f"Connected user {USER_ID} to provider fitbit"}
        )
    )

    async with make_client() as client:
        user = await client.create_user("demo")
        result = await client.connect_demo_provider(user.user_id, "fitbit")

    assert user.user_id == USER_ID
    assert result.success is True
    assert json.loads(connect.calls.last.request.read()) == {
        "user_id": USER_ID,
        "provider": "fitbit",
    }


def test_descriptor_labels_live_data_with_provider_attribution():
    descriptor = make_client(provider="oura").describe()
    assert descriptor.is_live is True
    assert descriptor.label == "Oura via Junction"
