"""Operation-specific OpenAPI examples; runtime error handling stays separate."""

from app.schemas.error import ErrorResponse


def not_found_response(code: str, message: str) -> dict:
    return {
        "model": ErrorResponse,
        "description": message,
        "content": {"application/json": {"example": {"error": {"code": code, "message": message}}}},
    }


def invalid_parameters_response() -> dict:
    return {
        "model": ErrorResponse,
        "description": "Invalid pagination or sort parameters.",
        "content": {
            "application/json": {
                "examples": {
                    "pagination": {
                        "value": {
                            "error": {"code": "INVALID_PAGINATION", "message": "page must be >= 1."}
                        }
                    },
                    "sort": {
                        "value": {
                            "error": {"code": "INVALID_SORT", "message": "Invalid sort field."}
                        }
                    },
                }
            }
        },
    }


def invalid_card_parameters_response() -> dict:
    response = invalid_parameters_response()
    response["description"] = "Invalid pagination, sort, or filter parameters."
    examples = response["content"]["application/json"]["examples"]
    for name, message in (
        ("chakra_range", "chakra_min cannot be greater than chakra_max."),
        ("power_range", "power_min cannot be greater than power_max."),
        ("negative_stat", "chakra_min must be greater than or equal to 0."),
    ):
        examples[name] = {"value": {"error": {"code": "INVALID_FILTER", "message": message}}}
    return response
