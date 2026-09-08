"""FastAPI dependencies.

The data source is resolved per request. That keeps the swap between Junction
and fixtures in one place, and scopes the HTTP connection pool to the request
that opened it.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request

from app.config import Settings, get_settings
from app.errors import ConfigurationError
from app.junction.client import JunctionClient
from app.junction.fixtures import FixtureDataSource
from app.junction.source import HealthDataSource
from app.services.pulse import PulseService


def provide_settings(request: Request) -> Settings:
    """Settings from app state when present, so tests can inject their own."""
    settings = getattr(request.app.state, "settings", None)
    return settings if isinstance(settings, Settings) else get_settings()


SettingsDep = Annotated[Settings, Depends(provide_settings)]


async def provide_source(settings: SettingsDep) -> AsyncIterator[HealthDataSource]:
    """Yield a live Junction client, or the local generator.

    In ``live`` mode a missing key or user id raises rather than silently
    falling back: being told the service is misconfigured is more useful than
    quietly being shown simulated numbers.
    """
    if settings.use_fixtures:
        yield FixtureDataSource(
            provider=settings.junction_provider,
            recent_days=settings.recent_days,
            history_days=settings.trend_days,
        )
        return

    if not settings.junction_api_key:
        raise ConfigurationError(
            "JUNCTION_API_KEY is not set. Add it to backend/.env, or set "
            "HEALTH_PULSE_DATA_SOURCE=fixture to run against generated data."
        )
    if not settings.junction_user_id:
        raise ConfigurationError(
            "JUNCTION_USER_ID is not set. Call POST /api/demo/provision to create a "
            "Junction demo patient, then put the returned user_id in backend/.env."
        )

    async with JunctionClient(
        api_key=settings.junction_api_key,
        user_id=settings.junction_user_id,
        base_url=settings.junction_base_url,
        provider=settings.junction_provider,
        timeout_seconds=settings.junction_timeout_seconds,
        max_retries=settings.junction_max_retries,
    ) as client:
        yield client


SourceDep = Annotated[HealthDataSource, Depends(provide_source)]


def provide_pulse_service(source: SourceDep, settings: SettingsDep) -> PulseService:
    return PulseService(source, settings)


PulseServiceDep = Annotated[PulseService, Depends(provide_pulse_service)]
