from pydantic import BaseModel, Field


class ReadyResponse(BaseModel):
    status: str = Field(examples=["ready", "not_ready"])

    model_config = {"json_schema_extra": {"example": {"status": "ready"}}}
