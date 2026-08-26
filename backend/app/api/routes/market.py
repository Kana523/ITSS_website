from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends

from app.api.dependencies import get_market_application_service
from app.api.schemas.industry import ApiModel
from app.market.application import (
    JitaSnapshotView,
    MarketApplicationService,
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


@router.get("/jita/status", response_model=JitaSnapshotResponse)
def jita_status(service: MarketServiceDependency) -> JitaSnapshotResponse:
    return _snapshot_response(service.jita_status())
