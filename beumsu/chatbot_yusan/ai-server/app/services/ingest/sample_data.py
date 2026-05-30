from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any

from app.services.translation.glossary import normalize_key


@dataclass
class Entity:
    id: str
    official_name_ko: str
    official_name_en: str
    official_name_zh: str
    official_name_ja: str
    hanja_name: str
    category: str
    period: str
    location_name: str
    description: str
    source_trust_level: str = "S1"


@dataclass
class Alias:
    id: str
    heritage_entity_id: str
    alias: str
    alias_normalized: str
    language: str
    alias_type: str
    confidence_prior: float = 1.0


@dataclass
class Document:
    id: str
    heritage_entity_id: str | None
    title: str
    source_type: str
    source_trust_level: str
    language: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Chunk:
    id: str
    document_id: str
    heritage_entity_id: str | None
    chunk_index: int
    content: str
    content_hash: str
    token_count: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Relation:
    id: str
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    description: str
    weight: float


class InMemoryHeritageStore:
    def __init__(self) -> None:
        self.entities: dict[str, Entity] = {}
        self.aliases: list[Alias] = []
        self.documents: dict[str, Document] = {}
        self.chunks: dict[str, Chunk] = {}
        self.relations: list[Relation] = []
        self.logs: list[dict[str, Any]] = []

    def seed_sample_data(self) -> dict[str, int]:
        self.entities.clear()
        self.aliases.clear()
        self.documents.clear()
        self.chunks.clear()
        self.relations.clear()
        entities = [
            Entity("gyeongbokgung", "경복궁", "Gyeongbokgung Palace", "景福宫", "景福宮", "景福宮", "palace", "조선", "서울 종로구", "조선 왕조의 법궁"),
            Entity("geunjeongjeon", "근정전", "Geunjeongjeon Hall", "勤政殿", "勤政殿", "勤政殿", "hall", "조선", "경복궁", "경복궁의 중심 건물"),
            Entity("gyeonghoeru", "경회루", "Gyeonghoeru Pavilion", "慶會樓", "慶會樓", "慶會樓", "pavilion", "조선", "경복궁", "연회와 사신 접대 공간"),
            Entity("hyangwonjeong", "향원정", "Hyangwonjeong Pavilion", "香遠亭", "香遠亭", "香遠亭", "pavilion", "조선", "경복궁", "후원 영역의 정자"),
            Entity("changdeokgung", "창덕궁", "Changdeokgung Palace", "昌德宮", "昌德宮", "昌德宮", "palace", "조선", "서울 종로구", "조선 궁궐"),
            Entity("changgyeonggung", "창경궁", "Changgyeonggung Palace", "昌慶宮", "昌慶宮", "昌慶宮", "palace", "조선", "서울 종로구", "조선 궁궐"),
            Entity("deoksugung", "덕수궁", "Deoksugung Palace", "德寿宫", "德壽宮", "德壽宮", "palace", "조선", "서울 중구", "조선 궁궐"),
            Entity("jongmyo", "종묘", "Jongmyo Shrine", "宗庙", "宗廟", "宗廟", "shrine", "조선", "서울 종로구", "조선 왕실 사당"),
        ]
        for entity in entities:
            self.entities[entity.id] = entity
        alias_map = {
            "gyeongbokgung": [("경복궁", "ko", "official", 1.0), ("경북궁", "ko", "typo", 0.93), ("경보궁", "ko", "typo", 0.88), ("景福宮", "zh", "hanja", 1.0), ("Gyeongbokgung", "en", "romanization", 1.0), ("Gyeongbokgung Palace", "en", "english", 1.0), ("Gyeongbok Palace", "en", "english", 0.98), ("Kyungbokgung", "en", "romanization", 0.92), ("Kyeongbokgung", "en", "romanization", 0.92)],
            "geunjeongjeon": [("근정전", "ko", "official", 1.0), ("勤政殿", "zh", "hanja", 1.0), ("Geunjeongjeon", "en", "romanization", 1.0), ("Geunjeongjeon Hall", "en", "english", 1.0)],
            "gyeonghoeru": [("경회루", "ko", "official", 1.0), ("慶會樓", "zh", "hanja", 1.0), ("Gyeonghoeru", "en", "romanization", 1.0), ("Gyeonghoeru Pavilion", "en", "english", 1.0)],
            "hyangwonjeong": [("향원정", "ko", "official", 1.0), ("香遠亭", "zh", "hanja", 1.0), ("Hyangwonjeong", "en", "romanization", 1.0), ("Hyangwonjeong Pavilion", "en", "english", 1.0)],
            "changdeokgung": [("창덕궁", "ko", "official", 1.0), ("昌德宮", "zh", "hanja", 1.0), ("Changdeokgung", "en", "romanization", 1.0), ("Changdeokgung Palace", "en", "english", 1.0)],
            "changgyeonggung": [("창경궁", "ko", "official", 1.0), ("Changgyeonggung", "en", "romanization", 1.0)],
            "deoksugung": [("덕수궁", "ko", "official", 1.0), ("Deoksugung", "en", "romanization", 1.0)],
            "jongmyo": [("종묘", "ko", "official", 1.0), ("宗廟", "zh", "hanja", 1.0), ("Jongmyo", "en", "romanization", 1.0)],
        }
        for eid, aliases in alias_map.items():
            for i, (alias, lang, alias_type, prior) in enumerate(aliases):
                self.aliases.append(Alias(f"{eid}-alias-{i}", eid, alias, normalize_key(alias), lang, alias_type, prior))
        docs = {
            "gyeongbokgung": "경복궁은 조선 왕조의 법궁으로 조선 시대 궁궐 문화와 왕실 의례를 이해하는 핵심 유산이다. 근정전, 경회루, 향원정 같은 주요 공간이 경복궁 안에 있다.",
            "geunjeongjeon": "근정전은 경복궁의 중심 건물로, 국가 의례와 공식 행사가 이루어진 정전이다.",
            "gyeonghoeru": "경회루는 경복궁 안에서 연회와 외국 사신 접대 등에 사용된 누각이다.",
            "hyangwonjeong": "향원정은 경복궁 후원 영역의 정자로, 휴식과 경관 감상을 위한 공간이다.",
            "changdeokgung": "창덕궁은 조선 시대 궁궐 유산이며 궁궐 건축과 후원 경관을 함께 이해할 수 있는 장소이다.",
            "changgyeonggung": "창경궁은 조선 시대 궁궐 유산으로 왕실 생활 공간과 관련된 장소이다.",
            "deoksugung": "덕수궁은 조선 궁궐 유산으로 근대기 왕실 공간의 변화를 살펴볼 수 있는 장소이다.",
            "jongmyo": "종묘는 조선 왕실의 사당으로 왕실 제례와 의례 문화를 이해하는 핵심 유산이다.",
        }
        for eid, content in docs.items():
            entity = self.entities[eid]
            doc = Document(f"doc-{eid}", eid, f"{entity.official_name_ko} sample official document", "official_db", "S1", "ko", content)
            self.documents[doc.id] = doc
            digest = sha256(content.encode()).hexdigest()
            self.chunks[f"chunk-{eid}-0"] = Chunk(f"chunk-{eid}-0", doc.id, eid, 0, content, digest, len(content.split()))
        self.relations.extend([
            Relation("rel-1", "gyeongbokgung", "geunjeongjeon", "contains", "경복궁 contains 근정전", 1.0),
            Relation("rel-2", "gyeongbokgung", "gyeonghoeru", "contains", "경복궁 contains 경회루", 1.0),
            Relation("rel-3", "gyeongbokgung", "hyangwonjeong", "contains", "경복궁 contains 향원정", 1.0),
            Relation("rel-4", "geunjeongjeon", "gyeongbokgung", "located_in", "근정전 located_in 경복궁", 0.9),
            Relation("rel-5", "geunjeongjeon", "gyeonghoeru", "nearby", "근정전 nearby 경회루", 0.5),
            Relation("rel-6", "gyeonghoeru", "hyangwonjeong", "route_next", "경회루 route_next 향원정", 0.8),
        ])
        return {"entities": len(self.entities), "aliases": len(self.aliases), "documents": len(self.documents), "chunks": len(self.chunks)}


store = InMemoryHeritageStore()
store.seed_sample_data()
