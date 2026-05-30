from typing import Any, Literal

from pydantic import BaseModel, Field


Audience = Literal["general", "child", "expert", "elderly", "visually_impaired", "hearing_impaired"]
Language = Literal["auto", "ko", "en", "zh", "ja", "unknown"]


class ChatOptions(BaseModel):
    include_citations: bool = True
    stream: bool = False
    tts_ready: bool = False


class Location(BaseModel):
    lat: float | None = None
    lng: float | None = None


class ChatRequest(BaseModel):
    session_id: str | None = None
    query: str
    language: Language = "auto"
    audience: Audience = "general"
    location: Location | None = None
    options: ChatOptions = Field(default_factory=ChatOptions)


class EntityMatch(BaseModel):
    heritage_id: str
    official_name_ko: str
    matched_alias: str
    match_type: str
    confidence: float
    confirmation_required: bool = False


class Citation(BaseModel):
    document_id: str
    chunk_id: str
    title: str
    source_type: str
    source_trust_level: str


class ImageAsset(BaseModel):
    image_id: str
    heritage_id: str
    title: str = ""
    image_url: str
    thumbnail_url: str | None = None
    caption: str = ""
    license_type: str = ""
    source_uri: str | None = None
    source_trust_level: str = "S1"


class ChatResponse(BaseModel):
    answer: str
    normalized_query: str
    detected_language: str
    intent: str
    entities: list[EntityMatch] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    images: list[ImageAsset] = Field(default_factory=list)
    confidence: float = 0.0
    follow_up_questions: list[str] = Field(default_factory=list)
    route: dict[str, Any] | None = None
    safety_flags: list[str] = Field(default_factory=list)
    latency_ms: int = 0
