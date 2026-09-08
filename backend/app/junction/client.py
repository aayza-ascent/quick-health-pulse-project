"""HTTP client for the Junction API.

Covers the four calls Health Pulse needs, per Junction's quickstart:

    POST /v2/user/                      create a patient
    POST /v2/link/connect/demo          attach a synthetic provider connection
    GET  /v2/summary/sleep/{user_id}    sleep sessions for a date range
    GET  /v2/summary/activity/{user_id} activity days for a date range

Reference: https://docs.junction.com/home/quickstart
"""

import asyncio
import logging
from datetime import date
from types import TracebackType
from typing import TypeVar

import httpx
from pydantic import ValidationError

from app.errors import (
    JunctionAuthError,
    JunctionError,
    JunctionNotFoundError,
    JunctionRateLimitError,
    JunctionUnavailableError,
)
from app.junction.models import (
    ActivityResponse,
    ActivitySummary,
    DemoConnection,
    JunctionModel,
    JunctionUser,
    SleepResponse,
    SleepSummary,
)
from app.junction.source import SourceDescriptor

logger = logging.getLogger("health_pulse.junction")

ModelT = TypeVar("ModelT", bound=JunctionModel)

API_KEY_HEADER = "x-vital-api-key"
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class JunctionClient:
    """Async client for Junction's summary endpoints.

    Usable as an async context manager, which is how the service layer scopes
    the underlying connection pool to a single request::

        async with JunctionClient(api_key=..., user_id=...) as junction:
            sleep = await junction.fetch_sleep(start, end)
    """

    def __init__(
        self,
        *,
        api_key: str,
        user_id: str,
        base_url: str = "https://api.sandbox.us.junction.com",
        provider: str = "fitbit",
        timeout_seconds: float = 10.0,
        max_retries: int = 2,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._user_id = user_id
        self._provider = provider
        self._max_retries = max_retries
        # The key lives only in this header. It is never logged and never
        # included in a response body, so it cannot leak to the browser.
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            headers={
                API_KEY_HEADER: api_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            transport=transport,
        )

    # --- lifecycle -----------------------------------------------------------

    async def __aenter__(self) -> "JunctionClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    # --- HealthDataSource ----------------------------------------------------

    def describe(self) -> SourceDescriptor:
        return SourceDescriptor(provider=self._provider, mode="junction")

    async def fetch_sleep(self, start: date, end: date) -> list[SleepSummary]:
        payload = await self._get(
            f"/v2/summary/sleep/{self._user_id}",
            params=_date_range(start, end),
        )
        return _parse(SleepResponse, payload).sleep

    async def fetch_activity(self, start: date, end: date) -> list[ActivitySummary]:
        payload = await self._get(
            f"/v2/summary/activity/{self._user_id}",
            params=_date_range(start, end),
        )
        return _parse(ActivityResponse, payload).activity

    # --- provisioning --------------------------------------------------------

    async def create_user(self, client_user_id: str) -> JunctionUser:
        """Create a Junction patient.

        ``client_user_id`` is our own identifier for the patient. Junction's
        docs are explicit that it must not carry PII, so Health Pulse uses an
        opaque slug rather than anything resembling a name or email.
        """
        payload = await self._post("/v2/user/", json={"client_user_id": client_user_id})
        return _parse(JunctionUser, payload)

    async def connect_demo_provider(self, user_id: str, provider: str) -> DemoConnection:
        """Attach a synthetic provider connection, backfilled with 30 days of data.

        Sandbox only. https://docs.junction.com/wearables/providers/test_data
        """
        payload = await self._post(
            "/v2/link/connect/demo",
            json={"user_id": user_id, "provider": provider},
        )
        return _parse(DemoConnection, payload)

    # --- transport -----------------------------------------------------------

    async def _get(self, path: str, *, params: dict[str, str] | None = None) -> object:
        return await self._request("GET", path, params=params)

    async def _post(self, path: str, *, json: dict[str, str]) -> object:
        return await self._request("POST", path, json=json)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json: dict[str, str] | None = None,
    ) -> object:
        """Issue a request, retrying transient failures with exponential backoff.

        Only 429 and 5xx responses and transport errors are retried. A 4xx is a
        problem with our request and will not fix itself, so it fails fast.
        """
        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                response = await self._http.request(method, path, params=params, json=json)
            except httpx.HTTPError as exc:
                last_error = JunctionUnavailableError(
                    f"Could not reach Junction: {exc.__class__.__name__}"
                )
                logger.warning("junction transport error on %s %s: %s", method, path, exc)
            else:
                if response.status_code < 400:
                    return response.json()
                if response.status_code not in RETRYABLE_STATUS:
                    raise _error_for_status(response)
                last_error = _error_for_status(response)
                logger.warning(
                    "junction returned %s on %s %s (attempt %s)",
                    response.status_code,
                    method,
                    path,
                    attempt + 1,
                )

            if attempt < self._max_retries:
                await asyncio.sleep(0.25 * 2**attempt)

        raise last_error or JunctionUnavailableError()


def _date_range(start: date, end: date) -> dict[str, str]:
    return {"start_date": start.isoformat(), "end_date": end.isoformat()}


def _error_for_status(response: httpx.Response) -> JunctionError:
    """Translate an HTTP status into the matching domain error."""
    status = response.status_code
    if status in (401, 403):
        return JunctionAuthError()
    if status == 404:
        return JunctionNotFoundError()
    if status == 429:
        return JunctionRateLimitError()
    if status >= 500:
        return JunctionUnavailableError(f"Junction returned {status}.")
    return JunctionError(f"Junction returned {status}.")


def _parse(model: type[ModelT], payload: object) -> ModelT:
    """Validate a response body, converting schema surprises into a domain error."""
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        logger.error("unexpected junction payload for %s: %s", model.__name__, exc)
        raise JunctionError("Junction returned a payload this service could not read.") from exc
