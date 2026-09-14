from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(examples=["ok"])
    version: str = Field(examples=["1.0.0"])

    model_config = {"json_schema_extra": {"example": {"status": "ok", "version": "1.0.0"}}}
