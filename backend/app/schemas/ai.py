from uuid import UUID

from pydantic import BaseModel, Field


class AIProcessingRequest(BaseModel):
    transcript_id: UUID
    task: str = Field(pattern="^(clean|translate|summary|minutes|action_items|topics|entities|qa)$")
    execution_target_kind: str = Field(default="automatic", pattern="^(automatic|local_model|api_provider)$")
    execution_target_id: UUID | None = None
    egress_acknowledged: bool = False
    options: dict = Field(default_factory=dict)
