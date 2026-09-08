"""FastAPI application factory."""

import logging
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import Settings, get_settings
from app.errors import HealthPulseError

logger = logging.getLogger("health_pulse")

API_TITLE = "Health Pulse API"
API_DESCRIPTION = (
    "Reads wearable summaries from Junction and reports how a recent window "
    "compares with the preceding baseline. Not a medical diagnostic tool."
)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application.

    Accepting settings lets tests construct an app with an explicit
    configuration instead of mutating the process environment.
    """
    settings = settings or get_settings()

    app = FastAPI(title=API_TITLE, description=API_DESCRIPTION, version="0.1.0")
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    _register_error_handlers(app)
    app.include_router(router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, object]:
        """Liveness probe that also reports which data source is in use.

        Useful when reviewing a running instance: it answers "is this reading
        real Junction data or local fixtures?" without inspecting the environment.
        """
        return {
            "status": "ok",
            "data_source": "fixture" if settings.use_fixtures else "junction",
            "junction_configured": settings.junction_is_configured,
        }

    return app


def _register_error_handlers(app: FastAPI) -> None:
    """Map domain errors onto a consistent JSON error envelope.

    The frontend switches on ``error.code``, so every failure the UI needs to
    distinguish is expressed there rather than in prose.
    """

    @app.exception_handler(HealthPulseError)
    async def handle_domain_error(_: Request, exc: HealthPulseError) -> JSONResponse:
        logger.warning("domain error: %s (%s)", exc.message, exc.code)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.middleware("http")
    async def catch_unhandled(
        request: Request,
        call_next: Callable[[Request], Awaitable[object]],
    ) -> object:
        try:
            return await call_next(request)
        except HealthPulseError:
            raise
        except Exception:
            logger.exception("unhandled error handling %s %s", request.method, request.url.path)
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "internal_error",
                        "message": "Something went wrong.",
                    }
                },
            )


app = create_app()
