from pydantic import BaseModel, Field


class RetrievalRequest(BaseModel):
    query: str
    normalized_entities: list = Field(default_factory=list)
    language: str = "ko"
    intent: str = "heritage_explanation"
    audience: str = "general"
    top_k: int = 8


class RetrievalResult(BaseModel):
    chunk_id: str
    document_id: str
    heritage_id: str | None
    title: str
    content: str
    source_type: str
    source_trust_level: str
    score: float
    score_breakdown: dict[str, float]
