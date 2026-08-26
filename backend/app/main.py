from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import install_error_handlers
from app.api.middleware import CalculationRequestGuardMiddleware
from app.api.routes.industry import router as industry_router
from app.api.routes.market import router as market_router
from app.api.specialist_skill_errors import install_specialist_skill_error_handler
from app.config import get_settings
from app.database.engine import is_database_available


def health(response: Response) -> dict[str, str]:
    database_status = "ok" if is_database_available() else "unavailable"

    if database_status != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {"api": "ok", "database": database_status}


def create_app(
    *,
    cors_origins: tuple[str, ...] | None = None,
    calculation_max_body_bytes: int | None = None,
    calculation_rate_limit_requests: int | None = None,
    calculation_rate_limit_window_seconds: int | None = None,
    calculation_max_concurrent_requests: int | None = None,
) -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="EVE Industry API",
        version="0.1.0",
    )
    application.add_middleware(
        CalculationRequestGuardMiddleware,
        max_body_bytes=(
            settings.calculation_max_body_bytes
            if calculation_max_body_bytes is None
            else calculation_max_body_bytes
        ),
        rate_limit_requests=(
            settings.calculation_rate_limit_requests
            if calculation_rate_limit_requests is None
            else calculation_rate_limit_requests
        ),
        rate_limit_window_seconds=(
            settings.calculation_rate_limit_window_seconds
            if calculation_rate_limit_window_seconds is None
            else calculation_rate_limit_window_seconds
        ),
        max_concurrent_requests=(
            settings.calculation_max_concurrent_requests
            if calculation_max_concurrent_requests is None
            else calculation_max_concurrent_requests
        ),
    )
    allowed_origins = (
        settings.allowed_cors_origins
        if cors_origins is None
        else cors_origins
    )
    if allowed_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(allowed_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
            max_age=600,
        )
    application.add_api_route(
        "/api/health",
        health,
        methods=["GET"],
        tags=["system"],
    )
    application.include_router(industry_router)
    application.include_router(market_router)
    install_error_handlers(application)
    install_specialist_skill_error_handler(application)
    return application


app = create_app()
