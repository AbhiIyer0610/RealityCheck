import asyncio
from contextlib import asynccontextmanager
import logging
from collections.abc import Callable

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.api.schemas import HealthResponse
from app.core.config import Settings, settings
from app.core.logging import configure_logging
from app.jobs.manager import JobManager

configure_logging()
logger = logging.getLogger(__name__)


def create_app(
    *,
    settings_override: Settings | None = None,
    manager_factory: Callable[[Settings], JobManager] | None = None,
) -> FastAPI:
    app_settings = settings_override or settings
    create_manager = manager_factory or JobManager

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        manager = create_manager(app_settings)
        application.state.settings = app_settings
        application.state.job_manager = manager
        application.state.upload_semaphore = asyncio.Semaphore(
            app_settings.max_concurrent_uploads
        )
        try:
            await manager.start()
            logger.info("RealityCheck API started in %s mode", app_settings.environment)
            yield
        finally:
            await manager.shutdown()
            logger.info("RealityCheck API stopped")

    application = FastAPI(
        title=app_settings.app_name,
        description=app_settings.app_description,
        version=app_settings.app_version,
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[app_settings.frontend_origin],
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
    )

    @application.middleware("http")
    async def reject_obviously_oversized_uploads(request: Request, call_next):
        if request.method == "POST" and request.url.path == "/api/v1/artifacts":
            content_length = request.headers.get("content-length")
            if content_length is not None:
                try:
                    request_bytes = int(content_length)
                except ValueError:
                    return JSONResponse(
                        status_code=400,
                        content={"detail": "Invalid Content-Length header."},
                    )
                # Allow multipart boundaries/headers; the endpoint separately enforces
                # the exact uploaded-file limit while reading the file.
                request_limit = app_settings.max_upload_size_mb * 1024 * 1024 + 64 * 1024
                if request_bytes > request_limit:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "The request exceeds the configured upload limit."},
                    )
        return await call_next(request)

    application.include_router(api_router, prefix="/api/v1")

    @application.get("/health", response_model=HealthResponse)
    async def health_check() -> HealthResponse:
        logger.debug("Health check requested")
        return HealthResponse(
            status="ok",
            service=app_settings.app_name,
            version=app_settings.app_version,
            environment=app_settings.environment,
        )

    @application.get("/ready")
    async def readiness_check() -> dict[str, str]:
        manager: JobManager | None = getattr(application.state, "job_manager", None)
        if manager is None or not await manager.health_check():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The service is not ready.",
            )
        return {"status": "ready"}

    return application


app = create_app()
