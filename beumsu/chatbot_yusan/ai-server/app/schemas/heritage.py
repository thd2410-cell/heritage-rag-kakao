from pydantic import BaseModel


class HeritageEntitySchema(BaseModel):
    id: str
    official_name_ko: str
    official_name_en: str
    official_name_zh: str
    official_name_ja: str
    hanja_name: str | None = None
    category: str = ""
    period: str = ""
    location_name: str = ""
    latitude: float | None = None
    longitude: float | None = None
    description: str = ""
    source_trust_level: str = "S1"


class HeritageAliasSchema(BaseModel):
    id: str
    heritage_entity_id: str
    alias: str
    alias_normalized: str
    language: str
    alias_type: str
    confidence_prior: float = 1.0
