"""API contract tests.

These exercise the wire format the frontend is typed against, and the two
properties that matter most for a service holding a third-party key: failures
are reported in a shape the UI can act on, and the key never leaves the server.
"""

from datetime import date, timedelta

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.api.dependencies import provide_source
from app.config import Settings
from app.errors import JunctionRateLimitError
from app.junction.fixtures import FixtureDataSource, FixtureProfile
from app.junction.models import ActivitySummary, SleepSummary
from app.junction.source import SourceDescriptor
from app.main import create_app

BASE_URL = "https://api.sandbox.us.junction.com"
USER_ID = "37c9c3fa-49e8-4d60-8cc8-328cba420f30"


def fixture_settings(**overrides: object) -> Settings:
    """Settings that ignore any .env on the developer's machine."""
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(fixture_settings()))


# --- meta --------------------------------------------------------------------


def test_health_reports_the_active_data_source(client: TestClient):
    body = client.get("/health").json()

    assert body == {"status": "ok", "data_source": "fixture", "junction_configured": False}


def test_openapi_schema_is_generated(client: TestClient):
    """A broken response model would surface here before it reached the UI."""
    schema = client.get("/openapi.json").json()

    assert "/api/pulse" in schema["paths"]
    assert "PulseOut" in schema["components"]["schemas"]


# --- the pulse payload -------------------------------------------------------


def test_pulse_returns_every_metric_with_a_verdict(client: TestClient):
    body = client.get("/api/pulse").json()

    assert [m["key"] for m in body["metrics"]] == ["sleep", "resting_heart_rate", "activity"]
    assert all(m["verdict"] for m in body["metrics"])
    assert all(m["summary"] for m in body["metrics"])


def test_pulse_surfaces_the_sleep_decline_as_the_headline(client: TestClient):
    body = client.get("/api/pulse").json()

    assert body["headline"]["metric"] == "sleep"
    assert body["headline"]["title"] == "Potential change worth reviewing"
    assert "decreased" in body["headline"]["body"]


def test_every_metric_carries_the_evidence_behind_it(client: TestClient):
    """An insight without its working is the thing this project exists to avoid."""
    body = client.get("/api/pulse").json()

    for metric in body["metrics"]:
        for window in (metric["baseline"], metric["recent"]):
            assert window["label"]
            assert window["start_date"] < window["end_date"]
            assert window["coverage"]["expected_days"] > 0
            assert window["coverage"]["observed_days"] <= window["coverage"]["expected_days"]
        assert metric["threshold_pct"] == 10.0
        assert metric["derivations"], "the field a metric came from must be reported"


def test_resting_heart_rate_evidence_shows_the_fallback_chain(client: TestClient):
    """Some nights have no hr_resting, so the evidence must name the substitute."""
    body = client.get("/api/pulse").json()
    metric = next(m for m in body["metrics"] if m["key"] == "resting_heart_rate")

    fields = {d["field"]: d["days"] for d in metric["derivations"]}
    assert "hr_resting" in fields
    assert "hr_lowest" in fields, "expected some nights to fall back"


def test_window_is_anchored_and_self_describing(client: TestClient):
    body = client.get("/api/pulse").json()
    window = body["window"]

    assert window["baseline_days"] == 21
    assert window["recent_days"] == 7
    assert window["baseline_end"] < window["recent_start"]
    assert window["recent_end"] == window["anchor_date"]


def test_disclaimer_is_part_of_the_payload(client: TestClient):
    """Shipped with the data, not left to the frontend to remember."""
    body = client.get("/api/pulse").json()

    assert "not a medical diagnostic tool" in body["disclaimer"]


def test_generated_data_is_never_labelled_as_coming_from_a_device(client: TestClient):
    body = client.get("/api/pulse").json()

    assert body["source"]["is_live"] is False
    assert body["source"]["label"] == "Simulated Fitbit data"
    assert body["patient"]["connection_status"] == "Demo data"


def test_no_notable_change_is_stated_rather_than_left_blank():
    """The default patient always has a decline, so this branch needs its own case.

    "Nothing crossed the threshold" is a finding, and the headline has to say so
    instead of collapsing to null and leaving an empty panel.
    """
    unchanging = FixtureProfile(
        baseline_sleep_seconds=27_000,
        recent_sleep_seconds=27_000,
        baseline_resting_hr=58.0,
        recent_resting_hr=58.0,
        baseline_steps=6_500,
        recent_steps=6_500,
        jitter=0.01,
    )

    app = create_app(fixture_settings())
    app.dependency_overrides[provide_source] = lambda: FixtureDataSource(profile=unchanging)

    body = TestClient(app).get("/api/pulse").json()

    assert body["headline"]["title"] == "No notable changes"
    assert body["headline"]["metric"] is None
    assert "10%" in body["headline"]["body"]
    assert "21-day baseline" in body["headline"]["body"]
    assert "not compared" not in body["headline"]["body"]
    assert all(m["direction"] == "stable" for m in body["metrics"])


def test_headline_names_metrics_that_could_not_be_compared():
    """Regression from live sandbox data.

    Junction's sandbox backfills 30 days of activity but only a handful of
    nights of sleep, so a real payload can pair a comparable metric with two
    that have too little coverage. The headline must not then claim every
    metric was within the threshold.
    """

    class SparseSleepSource:
        """Full activity coverage, sleep only on the most recent day."""

        def describe(self) -> SourceDescriptor:
            return SourceDescriptor(provider="fitbit", mode="junction")

        async def fetch_sleep(self, start: date, end: date) -> list[SleepSummary]:
            return [
                SleepSummary.model_validate(
                    {"calendar_date": end.isoformat(), "total": 27_000, "hr_lowest": 60}
                )
            ]

        async def fetch_activity(self, start: date, end: date) -> list[ActivitySummary]:
            days = (end - start).days
            return [
                ActivitySummary.model_validate(
                    {
                        "calendar_date": (start + timedelta(days=offset)).isoformat(),
                        "steps": 7_000,
                    }
                )
                for offset in range(days + 1)
            ]

    app = create_app(fixture_settings())
    app.dependency_overrides[provide_source] = lambda: SparseSleepSource()

    body = TestClient(app).get("/api/pulse").json()
    headline = body["headline"]["body"]

    assert "Sleep and Resting Heart Rate were not compared" in headline
    assert "every tracked metric is within" not in headline.lower()

    verdicts = {m["key"]: m["direction"] for m in body["metrics"]}
    assert verdicts["activity"] == "stable"
    assert verdicts["sleep"] == "insufficient_data"


# --- gaps --------------------------------------------------------------------


def test_trend_returns_gaps_as_nulls_rather_than_omitting_them(client: TestClient):
    """The chart needs to draw the gap, so the days must be present."""
    body = client.get("/api/pulse").json()
    trend = next(t for t in body["trends"] if t["key"] == "sleep")

    assert len(trend["points"]) == 30
    assert any(point["value"] is None for point in trend["points"])
    assert trend["coverage"]["observed_days"] < trend["coverage"]["expected_days"]

    days = [point["day"] for point in trend["points"]]
    assert days == sorted(days), "points must be chronological"


def test_no_gap_is_reported_as_zero(client: TestClient):
    body = client.get("/api/pulse").json()

    for trend in body["trends"]:
        for point in trend["points"]:
            assert point["value"] is None or point["value"] > 0


# --- dedicated endpoints -----------------------------------------------------


def test_sleep_endpoint_returns_the_nightly_series(client: TestClient):
    body = client.get("/api/patient/sleep").json()

    assert body["key"] == "sleep"
    assert body["unit"] == "seconds"
    assert len(body["points"]) == 30


def test_metrics_endpoint_returns_the_comparison_list(client: TestClient):
    body = client.get("/api/patient/metrics").json()

    assert len(body) == 3
    assert {m["key"] for m in body} == {"sleep", "resting_heart_rate", "activity"}


def test_patient_endpoint_describes_the_connection(client: TestClient):
    body = client.get("/api/patient").json()

    assert body["name"] == "Demo Patient"
    assert body["provider_label"] == "Fitbit"


# --- failure handling --------------------------------------------------------


def test_live_mode_without_a_key_explains_the_misconfiguration():
    """Better to say the service is unconfigured than to quietly show fixtures."""
    app = create_app(fixture_settings(health_pulse_data_source="live"))

    response = TestClient(app, raise_server_exceptions=False).get("/api/pulse")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "not_configured"
    assert "JUNCTION_API_KEY" in response.json()["error"]["message"]


def test_live_mode_without_a_user_id_points_at_the_provisioning_endpoint():
    app = create_app(fixture_settings(health_pulse_data_source="live", junction_api_key="test-key"))

    body = TestClient(app, raise_server_exceptions=False).get("/api/pulse").json()

    assert body["error"]["code"] == "not_configured"
    assert "/api/demo/provision" in body["error"]["message"]


def test_junction_failure_is_reported_in_a_shape_the_ui_can_branch_on():
    app = create_app(fixture_settings())

    class FailingSource:
        def describe(self) -> SourceDescriptor:
            return SourceDescriptor(provider="fitbit", mode="junction")

        async def fetch_sleep(self, start: object, end: object) -> list[object]:
            raise JunctionRateLimitError()

        async def fetch_activity(self, start: object, end: object) -> list[object]:
            return []

    app.dependency_overrides[provide_source] = lambda: FailingSource()
    response = TestClient(app, raise_server_exceptions=False).get("/api/pulse")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "junction_rate_limited"


# --- key handling ------------------------------------------------------------


@respx.mock
def test_api_key_never_appears_in_a_response_body():
    """The reason the frontend talks to this service instead of to Junction."""
    secret = "sk-sandbox-must-not-leak"
    respx.get(url__startswith=f"{BASE_URL}/v2/summary/sleep/").mock(
        return_value=httpx.Response(200, json={"sleep": []})
    )
    respx.get(url__startswith=f"{BASE_URL}/v2/summary/activity/").mock(
        return_value=httpx.Response(200, json={"activity": []})
    )

    app = create_app(
        fixture_settings(
            health_pulse_data_source="live",
            junction_api_key=secret,
            junction_user_id=USER_ID,
        )
    )
    response = TestClient(app, raise_server_exceptions=False).get("/api/pulse")

    assert response.status_code == 200
    assert secret not in response.text


@respx.mock
def test_provisioning_returns_the_user_id_and_the_next_step():
    respx.post(f"{BASE_URL}/v2/user/").mock(
        return_value=httpx.Response(200, json={"user_id": USER_ID})
    )
    respx.post(f"{BASE_URL}/v2/link/connect/demo").mock(
        return_value=httpx.Response(200, json={"success": True, "detail": "Connected"})
    )

    app = create_app(fixture_settings(health_pulse_data_source="live", junction_api_key="test-key"))
    body = TestClient(app).post("/api/demo/provision").json()

    assert body["user_id"] == USER_ID
    assert body["connected"] is True
    assert f"JUNCTION_USER_ID={USER_ID}" in body["next_step"]
    assert "expire after 7 days" in body["next_step"]


def test_empty_junction_response_is_reported_as_insufficient_not_as_zero():
    """A brand-new connection with no data must not read as a 100% decline."""

    class EmptySource:
        def describe(self) -> SourceDescriptor:
            return SourceDescriptor(provider="fitbit", mode="junction")

        async def fetch_sleep(self, start: object, end: object) -> list[object]:
            return []

        async def fetch_activity(self, start: object, end: object) -> list[object]:
            return []

    app = create_app(fixture_settings())
    app.dependency_overrides[provide_source] = lambda: EmptySource()

    body = TestClient(app).get("/api/pulse").json()

    for metric in body["metrics"]:
        assert metric["direction"] == "insufficient_data"
        assert metric["pct_change"] is None
        assert metric["insufficient_reason"] == "no_recent_data"
