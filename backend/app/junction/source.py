"""The seam between Health Pulse and its data provider.

Everything above this module works against :class:`HealthDataSource`, never
against ``httpx`` directly. That gives two concrete implementations for free:
the real Junction client, and a deterministic local generator used for tests
and for running the app before any credentials exist.
"""

from dataclasses import dataclass
from datetime import date
from typing import Literal, Protocol, runtime_checkable

from app.junction.models import ActivitySummary, SleepSummary

SourceMode = Literal["junction", "fixture"]

# Human-readable names for Junction's provider slugs, used for attribution in
# the UI. Unknown slugs fall back to a title-cased version of the slug itself.
PROVIDER_LABELS = {
    "apple_health_kit": "Apple Health",
    "fitbit": "Fitbit",
    "freestyle_libre": "FreeStyle Libre",
    "oura": "Oura",
}


def provider_label(slug: str) -> str:
    return PROVIDER_LABELS.get(slug, slug.replace("_", " ").title())


@dataclass(frozen=True)
class SourceDescriptor:
    """Provenance for a set of measurements, surfaced to the user verbatim.

    The UI shows this rather than hard-coding "Fitbit", because attribution is
    part of the product: a number is only trustworthy if you can see where it
    came from — including when it came from a local generator.
    """

    provider: str
    mode: SourceMode

    @property
    def label(self) -> str:
        if self.mode == "fixture":
            return f"Simulated {provider_label(self.provider)} data"
        return f"{provider_label(self.provider)} via Junction"

    @property
    def is_live(self) -> bool:
        return self.mode == "junction"


@runtime_checkable
class HealthDataSource(Protocol):
    """Read-only access to a patient's wearable summaries.

    Both methods return whatever the provider actually recorded for the range.
    Days with no measurement are simply absent from the list; filling the gaps
    is the caller's decision, made explicitly in :mod:`app.domain.series`.
    """

    def describe(self) -> SourceDescriptor:
        """Where this data comes from."""
        ...

    async def fetch_sleep(self, start: date, end: date) -> list[SleepSummary]:
        """Sleep sessions with a calendar date in ``[start, end]``."""
        ...

    async def fetch_activity(self, start: date, end: date) -> list[ActivitySummary]:
        """Activity days with a calendar date in ``[start, end]``."""
        ...
