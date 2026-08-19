from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_market_application_service
from app.api.schemas.industry import ApiModel
from app.market.application import (
    JitaRefreshView,
    JitaSnapshotView,
    MarketApplicationService,
)
from app.market.errors import (
    EsiRateLimitError,
    MarketCacheError,
    MarketRefreshInProgressError,
)


router = APIRouter(prefix="/api/market", tags=["market"])
MarketServiceDependency = Annotated[
    MarketApplicationService,
    Depends(get_market_application_service),
]


class JitaSnapshotResponse(ApiModel):
    region_id: int
    location_id: int
    location_name: str
    status: Literal["fresh", "stale", "unavailable"]
    fetched_at: datetime | None
    fresh_until: datetime | None
    age_minutes: int | None
    row_count: int


class JitaRefreshResponse(ApiModel):
    refresh_status: Literal["fresh", "updated", "not_modified"]
    snapshot: JitaSnapshotResponse


def _snapshot_response(view: JitaSnapshotView) -> JitaSnapshotResponse:
    return JitaSnapshotResponse(
        region_id=view.region_id,
        location_id=view.location_id,
        location_name=view.location_name,
        status=view.status.value,
        fetched_at=view.fetched_at,
        fresh_until=view.fresh_until,
        age_minutes=view.age_minutes,
        row_count=view.row_count,
    )


def _refresh_response(view: JitaRefreshView) -> JitaRefreshResponse:
    return JitaRefreshResponse(
        refresh_status=view.refresh_status.value,
        snapshot=_snapshot_response(view.snapshot),
    )


@router.get("/jita/status", response_model=JitaSnapshotResponse)
def jita_status(service: MarketServiceDependency) -> JitaSnapshotResponse:
    return _snapshot_response(service.jita_status())


@router.post(
    "/jita/refresh",
    response_model=JitaRefreshResponse,
    responses={
        409: {"description": "A market refresh is already running"},
        429: {"description": "ESI rate limit does not permit a refresh"},
        502: {"description": "ESI market refresh failed"},
    },
)
def refresh_jita_prices(service: MarketServiceDependency) -> JitaRefreshResponse:
    try:
        return _refresh_response(service.refresh_jita_prices())
    except MarketRefreshInProgressError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "market_refresh_in_progress",
                "message": str(exc),
            },
        ) from exc
    except EsiRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "esi_rate_limited",
                "message": str(exc),
                "retry_after_seconds": exc.retry_after_seconds,
            },
        ) from exc
    except MarketCacheError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "market_refresh_failed",
                "message": "Jita market refresh failed",
            },
        ) from exc
