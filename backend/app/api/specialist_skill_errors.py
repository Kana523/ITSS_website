from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.api.errors import _error_response
from app.industry.specialist_skills import MissingSpecialistSkillsError


async def missing_specialist_skills_error_handler(
    _request: Request,
    exc: MissingSpecialistSkillsError,
) -> JSONResponse:
    return _error_response(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "missing_specialist_skills",
        str(exc),
        {
            "missing_skills": [
                {
                    "recipe_key": {
                        "blueprint_type_id": recipe_key.blueprint_type_id,
                        "activity_id": recipe_key.activity_id,
                    },
                    "skill_type_id": requirement.type_id,
                    "current_level": current_level,
                    "required_level": requirement.level,
                }
                for recipe_key, requirement, current_level in exc.missing
            ]
        },
        sde_build_number=exc.sde_build_number,
    )


def install_specialist_skill_error_handler(application: FastAPI) -> None:
    application.add_exception_handler(
        MissingSpecialistSkillsError,
        missing_specialist_skills_error_handler,
    )
