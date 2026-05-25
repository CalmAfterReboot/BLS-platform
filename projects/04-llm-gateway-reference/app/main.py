"""FastAPI application entrypoint for the BLS AI Gateway."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.errors import AllProvidersFailedError, GatewayError
from app.models import CompletionRequest, CompletionResponse, Tier
from app.providers.registry import build_registry
from app.routing import Router

logger = logging.getLogger(__name__)


def _configure_logging(level: str) -> None:
    """Apply the configured log level to the root logger."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build the provider registry and Router once, on startup."""
    settings = get_settings()
    _configure_logging(settings.log_level)

    registry = build_registry(settings)
    router = Router(registry, settings)

    app.state.settings = settings
    app.state.registry = registry
    app.state.router = router

    logger.info(
        "gateway started with providers=%s",
        sorted(registry.keys()),
    )
    try:
        yield
    finally:
        logger.info("gateway shutting down")


def _error_envelope(
    error_type: str,
    message: str,
    **extra: object,
) -> dict[str, object]:
    """Build the structured JSON error envelope returned by exception handlers."""
    body: dict[str, object] = {"type": error_type, "message": message}
    body.update(extra)
    return {"error": body}


def create_app() -> FastAPI:
    """Build a fresh FastAPI app instance.

    Decorators register routes and handlers at function-call time, so each
    invocation returns an independently configured app. The module-level
    ``app = create_app()`` below is the canonical instance used by uvicorn
    and by the default test fixtures; tests that need parallel app instances
    (e.g. to set env overrides before the lifespan runs) can call this
    function directly.
    """
    app = FastAPI(
        title="BLS AI Gateway",
        description="HTTP gateway that routes LLM completion requests across multiple providers.",
        version="0.2.0",
        lifespan=lifespan,
    )

    @app.exception_handler(AllProvidersFailedError)
    async def _all_providers_failed_handler(
        request: Request,
        exc: AllProvidersFailedError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content=_error_envelope(
                error_type=type(exc).__name__,
                message=str(exc),
                tier=exc.tier.value,
                attempts=exc.attempts,
            ),
        )

    @app.exception_handler(GatewayError)
    async def _gateway_error_handler(request: Request, exc: GatewayError) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content=_error_envelope(
                error_type=type(exc).__name__,
                message=str(exc),
            ),
        )

    @app.get("/health")
    async def health(request: Request) -> dict[str, object]:
        """Liveness probe — reports status and which providers are registered."""
        registry: dict[str, object] = request.app.state.registry
        return {"status": "ok", "providers": sorted(registry.keys())}

    @app.get("/v1/providers")
    async def list_providers(request: Request) -> dict[str, object]:
        """Return the registered providers and the effective chain for each tier."""
        registry: dict[str, object] = request.app.state.registry
        router: Router = request.app.state.router
        return {
            "providers": sorted(registry.keys()),
            "chains": {tier.value: router.effective_chain(tier) for tier in Tier},
        }

    @app.post("/v1/complete", response_model=CompletionResponse)
    async def complete(payload: CompletionRequest, request: Request) -> CompletionResponse:
        """Route a completion request through the tier chain and return the response."""
        router: Router = request.app.state.router
        return await router.route(payload)

    return app


app = create_app()
