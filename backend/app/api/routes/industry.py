from fractions import Fraction
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.api.dependencies import get_industry_application_service
from app.api.schemas.errors import ErrorResponse
from app.api.schemas.industry import (
    ProductRecipesResponse,
    TypeSearchQuery,
    TypeSearchResponse,
    product_recipes_response,
    type_search_response,
)
from app.api.schemas.industry_calculation import (
    IndustryCalculationRequest,
    IndustryCalculationResponse,
    industry_calculation_response,
)
from app.industry.application import IndustryApplicationService


router = APIRouter(prefix="/api/industry", tags=["industry"])
IndustryServiceDependency = Annotated[
    IndustryApplicationService,
    Depends(get_industry_application_service),
]
ERROR_RESPONSES = {
    404: {"model": ErrorResponse, "description": "EVE type not found"},
    409: {"model": ErrorResponse, "description": "Plan conflict"},
    413: {"model": ErrorResponse, "description": "Request body too large"},
    429: {"model": ErrorResponse, "description": "Too many requests"},
    422: {"model": ErrorResponse, "description": "Invalid request"},
    500: {"model": ErrorResponse, "description": "Internal server error"},
    503: {"model": ErrorResponse, "description": "Data unavailable"},
}


@router.get(
    "/types",
    response_model=TypeSearchResponse,
    responses={
        422: ERROR_RESPONSES[422],
        500: ERROR_RESPONSES[500],
        503: ERROR_RESPONSES[503],
    },
)
def search_types(
    query: Annotated[TypeSearchQuery, Query()],
    service: IndustryServiceDependency,
) -> TypeSearchResponse:
    result = service.search_types(
        query.search,
        producible_only=query.producible_only,
        limit=query.limit,
    )
    return type_search_response(
        result,
        query=query.search,
        limit=query.limit,
    )


@router.get(
    "/recipes/{product_type_id}",
    response_model=ProductRecipesResponse,
    responses={
        404: ERROR_RESPONSES[404],
        422: ERROR_RESPONSES[422],
        500: ERROR_RESPONSES[500],
        503: ERROR_RESPONSES[503],
    },
)
def get_product_recipes(
    product_type_id: Annotated[int, Path(gt=0, le=2_147_483_647)],
    service: IndustryServiceDependency,
) -> ProductRecipesResponse:
    return product_recipes_response(
        service.get_product_recipes(product_type_id)
    )


@router.post(
    "/calculate",
    response_model=IndustryCalculationResponse,
    responses={
        404: ERROR_RESPONSES[404],
        409: ERROR_RESPONSES[409],
        413: ERROR_RESPONSES[413],
        422: ERROR_RESPONSES[422],
        429: ERROR_RESPONSES[429],
        500: ERROR_RESPONSES[500],
        503: ERROR_RESPONSES[503],
    },
)
def calculate(
    request: IndustryCalculationRequest,
    service: IndustryServiceDependency,
) -> IndustryCalculationResponse:
    implant = request.to_manufacturing_time_implant()
    owned_materials = request.to_owned_materials()
    result = service.create_plan(
        request.to_demands(),
        choices=request.to_choices(),
        blueprint_efficiencies=request.to_blueprint_efficiencies(),
        production_profile=request.to_production_profile(),
        owned_materials=owned_materials,
        blueprint_copy_run_limits=request.to_blueprint_copy_run_limits(),
        specialist_skill_levels=request.to_specialist_skill_levels(),
        pricing_options=request.to_pricing_options(),
        manufacturing_time_multiplier=(
            implant.time_multiplier if implant is not None else Fraction(1)
        ),
        expected_sde_build_number=request.expected_sde_build_number,
    )
    return industry_calculation_response(
        result,
        implant,
        owned_materials_included=bool(owned_materials),
    )
