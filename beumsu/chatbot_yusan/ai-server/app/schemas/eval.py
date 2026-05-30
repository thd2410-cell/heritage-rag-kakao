from pydantic import BaseModel, Field


class EvaluationCaseSchema(BaseModel):
    id: str
    question: str
    expected_entity_id: str | None = None
    expected_intent: str | None = None
    expected_source_ids: list[str] = Field(default_factory=list)
    language: str = "ko"
    audience: str = "general"
    tags: list[str] = Field(default_factory=list)
