"""HTTP endpoints.

Every route is a thin translation of a service call into the wire schema. The
frontend calls these and never Junction directly, so the API key stays on the
server.
"""

from fastapi import APIRouter

from app.api.dependencies import PulseServiceDep, SettingsDep
from app.api.schemas import (
    MetricChangeOut,
    PatientOut,
    ProvisionResultOut,
    PulseOut,
    TrendOut,
)
from app.domain.metrics import MetricKey
from app.errors import ConfigurationError
from app.junction.client import JunctionClient

router = APIRouter(prefix="/api", tags=["pulse"])


@router.get("/pulse", response_model=PulseOut, summary="Everything behind one dashboard render")
async def get_pulse(service: PulseServiceDep) -> PulseOut:
    """The full payload: metrics, the change worth reviewing, evidence and trends.

    Served as one call because the figures and the evidence explaining them must
    come from a single computation. Fetching them separately would let the two
    drift apart between requests.
    """
    return PulseOut.of(await service.build())


@router.get("/patient", response_model=PatientOut, summary="Demo patient and connection")
async def get_patient(service: PulseServiceDep) -> PatientOut:
    pulse = await service.build()
    return PulseOut.of(pulse).patient


@router.get(
    "/patient/metrics",
    response_model=list[MetricChangeOut],
    summary="Every tracked metric with its baseline comparison",
)
async def get_metrics(service: PulseServiceDep) -> list[MetricChangeOut]:
    pulse = await service.build()
    return [MetricChangeOut.of(change) for change in pulse.changes.values()]


@router.get(
    "/patient/sleep",
    response_model=TrendOut,
    summary="Nightly sleep duration, with gaps preserved",
)
async def get_sleep(service: PulseServiceDep) -> TrendOut:
    """Sleep is the priority metric, so it also gets a dedicated endpoint.

    Points with a null value are days the provider recorded nothing. They are
    returned rather than omitted so the client can render the gap.
    """
    pulse = await service.build()
    return TrendOut.of(pulse.changes[MetricKey.SLEEP], pulse.trends[MetricKey.SLEEP])


@router.post(
    "/demo/provision",
    response_model=ProvisionResultOut,
    summary="Create a Junction demo patient and attach a synthetic connection",
)
async def provision_demo_patient(settings: SettingsDep) -> ProvisionResultOut:
    """One-time setup against Junction's sandbox.

    Creates a user, attaches a demo provider connection (which Junction
    backfills with 30 days of synthetic data), and returns the user id to put
    in ``.env``. Kept as an explicit endpoint rather than run at startup: it
    creates remote state and counts against the sandbox user limit, so it
    should happen when asked for, not on every boot.
    """
    if not settings.junction_api_key:
        raise ConfigurationError("JUNCTION_API_KEY is not set, so no patient can be created.")

    async with JunctionClient(
        api_key=settings.junction_api_key,
        # No user exists yet; the placeholder is unused by the calls below.
        user_id="",
        base_url=settings.junction_base_url,
        provider=settings.junction_provider,
        timeout_seconds=settings.junction_timeout_seconds,
        max_retries=settings.junction_max_retries,
    ) as client:
        user = await client.create_user(settings.junction_client_user_id)
        connection = await client.connect_demo_provider(user.user_id, settings.junction_provider)

    return ProvisionResultOut(
        user_id=user.user_id,
        provider=settings.junction_provider,
        connected=connection.success,
        detail=connection.detail,
        next_step=(
            f"Set JUNCTION_USER_ID={user.user_id} in backend/.env and restart the service. "
            "Junction demo users expire after 7 days."
        ),
    )
