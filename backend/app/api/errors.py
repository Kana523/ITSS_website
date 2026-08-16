import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import (
    OperationalError,
    SQLAlchemyError,
    TimeoutError as SQLAlchemyTimeoutError,
)

from app.industry.errors import (
    AmbiguousRecipeError,
    BlueprintEfficiencyNotApplicableError,
    ConflictingRigModifiersError,
    IndustryError,
    InvalidIndustryDataError,
    InvalidRecipeChoiceError,
    MissingActivityPricingError,
    MissingRecipeError,
    PlanTooLargeError,
    QuantityTooLargeError,
    RecipeCycleError,
    SdeNotImportedError,
    SdeVersionMismatchError,
    UnknownTypeError,
    UnpublishedTypeError,
    UnusedBlueprintEfficienciesError,
    UnusedBuildChoicesError,
    UnsupportedCoProductsError,
)
from app.industry.valuation import InvalidValuationDataError


logger = logging.getLogger(__name__)


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    *,
    sde_build_number: int | None = None,
) -> JSONResponse:
    content: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "details": details,
        }
    }
    if sde_build_number is not None:
        content["sde_build_number"] = sde_build_number
    return JSONResponse(
        status_code=status_code,
        content=content,
    )


async def request_validation_error_handler(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    return _error_response(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "validation_error",
        "Request validation failed",
        {"errors": jsonable_encoder(exc.errors())},
    )


async def industry_error_handler(
    _request: Request,
    exc: IndustryError,
) -> JSONResponse:
    if isinstance(exc, SdeNotImportedError):
        return _error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "sde_not_imported",
            str(exc),
        )
    if isinstance(exc, SdeVersionMismatchError):
        return _error_response(
            status.HTTP_409_CONFLICT,
            "sde_version_mismatch",
            str(exc),
            {
                "expected_sde_build_number": exc.expected_build,
                "current_sde_build_number": exc.current_build,
            },
            sde_build_number=exc.current_build,
        )
    if isinstance(exc, UnknownTypeError):
        return _error_response(
            status.HTTP_404_NOT_FOUND,
            "unknown_type",
            str(exc),
            {"type_ids": list(exc.type_ids)},
            sde_build_number=exc.sde_build_number,
        )
    if isinstance(exc, UnpublishedTypeError):
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "unpublished_type",
            str(exc),
            {"type_ids": list(exc.type_ids)},
            sde_build_number=exc.sde_build_number,
        )
    if isinstance(exc, AmbiguousRecipeError):
        return _error_response(
            status.HTTP_409_CONFLICT,
            "ambiguous_recipe",
            str(exc),
            {
                "product_type_id": exc.product_type_id,
                "candidates": [
                    {
                        "blueprint_type_id": candidate.blueprint_type_id,
                        "activity_id": candidate.activity_id,
                    }
                    for candidate in exc.candidates
                ],
            },
            sde_build_number=exc.sde_build_number,
        )
    if isinstance(exc, MissingRecipeError):
        return _error_response(
            status.HTTP_409_CONFLICT,
            "missing_recipe",
            str(exc),
            {"product_type_id": exc.product_type_id},
            sde_build_number=exc.sde_build_number,
        )
    if isinstance(exc, InvalidRecipeChoiceError):
        return _error_response(
            status.HTTP_409_CONFLICT,
            "invalid_recipe_choice",
            str(exc),
            {
                "product_type_id": exc.product_type_id,
                "recipe_key": {
                    "blueprint_type_id": exc.recipe_key.blueprint_type_id,
                    "activity_id": exc.recipe_key.activity_id,
                },
            },
            sde_build_number=exc.sde_build_number,
        )
    if isinstance(exc, RecipeCycleError):
        return _error_response(
            status.HTTP_409_CONFLICT,
            "recipe_cycle",
            str(exc),
            {
                "type_path": list(exc.type_path),
                "hint": "Mark one type in the cycle as buy to stop recursion",
            },
            sde_build_number=exc.sde_build_number,
        )
    if isinstance(exc, UnsupportedCoProductsError):
        return _error_response(
            status.HTTP_409_CONFLICT,
            "unsupported_co_products",
            str(exc),
            {
                "recipe_key": {
                    "blueprint_type_id": exc.recipe_key.blueprint_type_id,
                    "activity_id": exc.recipe_key.activity_id,
                }
            },
            sde_build_number=exc.sde_build_number,
        )
    if isinstance(exc, PlanTooLargeError):
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "plan_too_large",
            str(exc),
            {"maximum_expanded_types": exc.maximum_types},
            sde_build_number=exc.sde_build_number,
        )
    if isinstance(exc, QuantityTooLargeError):
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "quantity_too_large",
            str(exc),
            {
                "field": exc.field_name,
                "maximum_safe_integer": exc.maximum,
            },
            sde_build_number=exc.sde_build_number,
        )
    if isinstance(exc, UnusedBuildChoicesError):
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "unused_build_choices",
            str(exc),
            {"type_ids": list(exc.type_ids)},
            sde_build_number=exc.sde_build_number,
        )
    if isinstance(exc, UnusedBlueprintEfficienciesError):
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "unused_blueprint_efficiencies",
            str(exc),
            {
                "recipe_keys": [
                    {
                        "blueprint_type_id": recipe_key.blueprint_type_id,
                        "activity_id": recipe_key.activity_id,
                    }
                    for recipe_key in exc.recipe_keys
                ]
            },
            sde_build_number=exc.sde_build_number,
        )
    if isinstance(exc, BlueprintEfficiencyNotApplicableError):
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "blueprint_efficiency_not_applicable",
            str(exc),
            {
                "recipe_key": {
                    "blueprint_type_id": exc.recipe_key.blueprint_type_id,
                    "activity_id": exc.recipe_key.activity_id,
                },
                "activity": exc.activity.value,
            },
            sde_build_number=exc.sde_build_number,
        )
    if isinstance(exc, ConflictingRigModifiersError):
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "conflicting_rig_modifiers",
            str(exc),
            {
                "recipe_key": {
                    "blueprint_type_id": exc.recipe_key.blueprint_type_id,
                    "activity_id": exc.recipe_key.activity_id,
                },
                "dimension": exc.dimension,
            },
            sde_build_number=exc.sde_build_number,
        )
    if isinstance(exc, MissingActivityPricingError):
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "missing_activity_pricing",
            str(exc),
            {"activities": [activity.value for activity in exc.activities]},
            sde_build_number=exc.sde_build_number,
        )
    if isinstance(exc, InvalidIndustryDataError):
        logger.error("Industry data invariant failed (%s)", type(exc).__name__)
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "industry_data_error",
            "Industry data is inconsistent",
        )
    return _error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "industry_error",
        "Industry operation failed",
    )


async def database_operational_error_handler(
    _request: Request,
    _exc: OperationalError | SQLAlchemyTimeoutError,
) -> JSONResponse:
    return _error_response(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "database_unavailable",
        "The industry database is temporarily unavailable",
    )


async def database_error_handler(
    _request: Request,
    exc: SQLAlchemyError,
) -> JSONResponse:
    logger.error(
        "Unhandled SQLAlchemy error in industry API (%s)",
        type(exc).__name__,
    )
    return _error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "database_error",
        "The industry database operation failed",
    )


async def valuation_data_error_handler(
    _request: Request,
    exc: InvalidValuationDataError,
) -> JSONResponse:
    logger.error(
        "Industry valuation invariant failed (%s)",
        type(exc).__name__,
    )
    return _error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "industry_data_error",
        "Industry pricing data is inconsistent",
    )


def install_error_handlers(application: FastAPI) -> None:
    application.add_exception_handler(
        RequestValidationError,
        request_validation_error_handler,
    )
    application.add_exception_handler(IndustryError, industry_error_handler)
    application.add_exception_handler(
        OperationalError,
        database_operational_error_handler,
    )
    application.add_exception_handler(
        SQLAlchemyTimeoutError,
        database_operational_error_handler,
    )
    application.add_exception_handler(SQLAlchemyError, database_error_handler)
    application.add_exception_handler(
        InvalidValuationDataError,
        valuation_data_error_handler,
    )
