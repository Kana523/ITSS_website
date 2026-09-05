from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_market_application_service
from app.api.schemas.industry import ApiModel
from app.market.application import (
    IndustryIndexSnapshotView,
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


IndustryActivityCode = Literal[
    "copying",
    "invention",
    "manufacturing",
    "reaction",
    "research_material",
    "research_time",
]


class IndustryIndexSnapshotResponse(ApiModel):
    solar_system_id: int
    activity: IndustryActivityCode
    cost_index: Decimal | None
    status: Literal["fresh", "stale", "unavailable"]
    fetched_at: datetime | None
    fresh_until: datetime | None
    age_minutes: int | None


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


def _index_snapshot_response(
    view: IndustryIndexSnapshotView,
) -> IndustryIndexSnapshotResponse:
    return IndustryIndexSnapshotResponse(
        solar_system_id=view.solar_system_id,
        activity=view.activity,
        cost_index=view.cost_index,
        status=view.status.value,
        fetched_at=view.fetched_at,
        fresh_until=view.fresh_until,
        age_minutes=view.age_minutes,
    )


@router.get(
    "/industry-index",
    response_model=IndustryIndexSnapshotResponse,
)
def industry_index(
    service: MarketServiceDependency,
    solar_system_id: Annotated[
        int,
        Query(gt=0, le=2_147_483_647),
    ],
    activity: Annotated[IndustryActivityCode, Query()],
) -> IndustryIndexSnapshotResponse:
    return _index_snapshot_response(
        service.system_cost_index(solar_system_id, activity)
    )
