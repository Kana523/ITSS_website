from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database.repositories.industry import SqlAlchemyIndustryRepository
from app.database.repositories.market import SqlAlchemyMarketCacheRepository
from app.database.session import get_db_session
from app.industry.application import IndustryApplicationService
from app.industry.economics_service import (
    IndustryEconomicsService,
    MarketContext,
)
from app.market.application import MarketApplicationService


DatabaseSession = Annotated[Session, Depends(get_db_session)]


def get_industry_repository(
    session: DatabaseSession,
) -> SqlAlchemyIndustryRepository:
    return SqlAlchemyIndustryRepository(session)


def get_market_repository(
    session: DatabaseSession,
) -> SqlAlchemyMarketCacheRepository:
    return SqlAlchemyMarketCacheRepository(session)


def get_market_application_service(
    market_repository: Annotated[
        SqlAlchemyMarketCacheRepository,
        Depends(get_market_repository),
    ],
) -> MarketApplicationService:
    return MarketApplicationService(market_repository, get_settings())


def get_industry_application_service(
    repository: Annotated[
        SqlAlchemyIndustryRepository,
        Depends(get_industry_repository),
    ],
    market_repository: Annotated[
        SqlAlchemyMarketCacheRepository,
        Depends(get_market_repository),
    ],
) -> IndustryApplicationService:
    settings = get_settings()
    return IndustryApplicationService(
        repository,
        IndustryEconomicsService(
            market_repository,
            MarketContext(
                region_id=settings.market_region_id,
                location_id=settings.market_location_id,
                location_name=settings.market_location_name,
            ),
            compatibility_date=settings.esi_compatibility_date,
        ),
    )
