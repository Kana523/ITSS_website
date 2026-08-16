from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import install_error_handlers
from app.api.routes.industry import router as industry_router
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
) -> FastAPI:
    application = FastAPI(
        title="EVE Industry API",
        version="0.1.0",
    )
    allowed_origins = (
        get_settings().allowed_cors_origins
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
    install_error_handlers(application)
    return application


app = create_app()
