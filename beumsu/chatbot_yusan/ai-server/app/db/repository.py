from __future__ import annotations

from hashlib import sha256
from itertools import count
import json
from typing import Iterable

from sqlalchemy import or_, select
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import (
    Base,
    DocumentChunk,
    HeritageAlias,
    HeritageDocument,
    HeritageEntity,
    HeritageImage,
    HeritageRelation,
)
from app.db.session import engine
from app.services.translation.glossary import normalize_key


class HeritageRepository:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def init_schema() -> None:
        if engine.url.get_backend_name().startswith("postgresql"):
            with engine.begin() as connection:
                connection.execute(sql_text("CREATE EXTENSION IF NOT EXISTS vector"))
        Base.metadata.create_all(bind=engine)
        if engine.url.get_backend_name().startswith("postgresql"):
            with engine.begin() as connection:
                connection.execute(
                    sql_text(
                        "ALTER TABLE document_chunks "
                        f"ADD COLUMN IF NOT EXISTS embedding_vector vector({settings.embedding_dimensions})"
                    )
                )
                connection.execute(
                    sql_text(
                        "CREATE INDEX IF NOT EXISTS document_chunks_embedding_vector_hnsw_idx "
                        "ON document_chunks USING hnsw (embedding_vector vector_cosine_ops)"
                    )
                )
                connection.execute(
                    sql_text(
                        "CREATE INDEX IF NOT EXISTS document_chunks_content_fts_idx "
                        "ON document_chunks USING gin (to_tsvector('simple', content))"
                    )
                )

    def seed_sample_data(self) -> dict[str, int]:
        entities = [
            HeritageEntity(id="gyeongbokgung", official_name_ko="경복궁", official_name_en="Gyeongbokgung Palace", official_name_zh="景福宫", official_name_ja="景福宮", hanja_name="景福宮", category="palace", period="조선", location_name="서울 종로구", description="조선 왕조의 법궁", source_trust_level="S1"),
            HeritageEntity(id="geunjeongjeon", official_name_ko="근정전", official_name_en="Geunjeongjeon Hall", official_name_zh="勤政殿", official_name_ja="勤政殿", hanja_name="勤政殿", category="hall", period="조선", location_name="경복궁", description="경복궁의 중심 건물", source_trust_level="S1"),
            HeritageEntity(id="gyeonghoeru", official_name_ko="경회루", official_name_en="Gyeonghoeru Pavilion", official_name_zh="慶會樓", official_name_ja="慶會樓", hanja_name="慶會樓", category="pavilion", period="조선", location_name="경복궁", description="연회와 사신 접대 공간", source_trust_level="S1"),
            HeritageEntity(id="hyangwonjeong", official_name_ko="향원정", official_name_en="Hyangwonjeong Pavilion", official_name_zh="香遠亭", official_name_ja="香遠亭", hanja_name="香遠亭", category="pavilion", period="조선", location_name="경복궁", description="후원 영역의 정자", source_trust_level="S1"),
            HeritageEntity(id="changdeokgung", official_name_ko="창덕궁", official_name_en="Changdeokgung Palace", official_name_zh="昌德宮", official_name_ja="昌德宮", hanja_name="昌德宮", category="palace", period="조선", location_name="서울 종로구", description="조선 궁궐", source_trust_level="S1"),
            HeritageEntity(id="changgyeonggung", official_name_ko="창경궁", official_name_en="Changgyeonggung Palace", official_name_zh="昌慶宮", official_name_ja="昌慶宮", hanja_name="昌慶宮", category="palace", period="조선", location_name="서울 종로구", description="조선 궁궐", source_trust_level="S1"),
            HeritageEntity(id="deoksugung", official_name_ko="덕수궁", official_name_en="Deoksugung Palace", official_name_zh="德寿宫", official_name_ja="德壽宮", hanja_name="德壽宮", category="palace", period="조선", location_name="서울 중구", description="조선 궁궐", source_trust_level="S1"),
            HeritageEntity(id="jongmyo", official_name_ko="종묘", official_name_en="Jongmyo Shrine", official_name_zh="宗庙", official_name_ja="宗廟", hanja_name="宗廟", category="shrine", period="조선", location_name="서울 종로구", description="조선 왕실 사당", source_trust_level="S1"),
        ]
        for entity in entities:
            self.db.merge(entity)
        self.db.flush()
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
                self.db.merge(HeritageAlias(id=f"{eid}-alias-{i}", heritage_entity_id=eid, alias=alias, alias_normalized=normalize_key(alias), language=lang, alias_type=alias_type, confidence_prior=prior))
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
            entity = next(e for e in entities if e.id == eid)
            doc = HeritageDocument(id=f"doc-{eid}", heritage_entity_id=eid, title=f"{entity.official_name_ko} sample official document", source_type="official_db", source_trust_level="S1", language="ko", content=content, doc_metadata={"sample": True})
            self.db.merge(doc)
            self.db.merge(DocumentChunk(id=f"chunk-{eid}-0", document_id=doc.id, heritage_entity_id=eid, chunk_index=0, content=content, content_hash=sha256(content.encode()).hexdigest(), token_count=len(content.split()), embedding=None, chunk_metadata={"sample": True}))
        relations = [
            HeritageRelation(id="rel-1", source_entity_id="gyeongbokgung", target_entity_id="geunjeongjeon", relation_type="contains", description="경복궁 contains 근정전", weight=1.0),
            HeritageRelation(id="rel-2", source_entity_id="gyeongbokgung", target_entity_id="gyeonghoeru", relation_type="contains", description="경복궁 contains 경회루", weight=1.0),
            HeritageRelation(id="rel-3", source_entity_id="gyeongbokgung", target_entity_id="hyangwonjeong", relation_type="contains", description="경복궁 contains 향원정", weight=1.0),
            HeritageRelation(id="rel-4", source_entity_id="geunjeongjeon", target_entity_id="gyeongbokgung", relation_type="located_in", description="근정전 located_in 경복궁", weight=0.9),
            HeritageRelation(id="rel-5", source_entity_id="geunjeongjeon", target_entity_id="gyeonghoeru", relation_type="nearby", description="근정전 nearby 경회루", weight=0.5),
            HeritageRelation(id="rel-6", source_entity_id="gyeonghoeru", target_entity_id="hyangwonjeong", relation_type="route_next", description="경회루 route_next 향원정", weight=0.8),
        ]
        for relation in relations:
            self.db.merge(relation)
        self.db.commit()
        return {"entities": self.db.scalar(select(HeritageEntity).count()) if False else len(entities), "aliases": sum(len(v) for v in alias_map.values()), "documents": len(docs), "chunks": len(docs)}

    def list_entities(self) -> list[HeritageEntity]:
        return list(self.db.scalars(select(HeritageEntity).order_by(HeritageEntity.official_name_ko)))

    def list_aliases(self) -> list[HeritageAlias]:
        return list(self.db.scalars(select(HeritageAlias)))

    def get_entity(self, entity_id: str) -> HeritageEntity | None:
        return self.db.get(HeritageEntity, entity_id)

    def related_entity_ids(self, entity_id: str) -> list[str]:
        rows = self.db.scalars(
            select(HeritageRelation).where(
                or_(HeritageRelation.source_entity_id == entity_id, HeritageRelation.target_entity_id == entity_id)
            )
        )
        related = []
        for row in rows:
            related.append(row.target_entity_id if row.source_entity_id == entity_id else row.source_entity_id)
        return related

    def search_chunks(self, entity_ids: Iterable[str] | None = None) -> list[tuple[DocumentChunk, HeritageDocument]]:
        stmt = select(DocumentChunk, HeritageDocument).join(HeritageDocument, DocumentChunk.document_id == HeritageDocument.id)
        ids = list(entity_ids or [])
        if ids:
            stmt = stmt.where(DocumentChunk.heritage_entity_id.in_(ids))
        return list(self.db.execute(stmt))

    def count_embedding_vectors(self) -> dict[str, int]:
        if not engine.url.get_backend_name().startswith("postgresql"):
            return {"total": 0, "embedded": 0, "missing": 0}
        row = self.db.execute(
            sql_text(
                "SELECT count(*) AS total, count(embedding_vector) AS embedded "
                "FROM document_chunks"
            )
        ).mappings().one()
        total = int(row["total"])
        embedded = int(row["embedded"])
        return {"total": total, "embedded": embedded, "missing": total - embedded}

    def chunks_missing_embedding(self, limit: int = 100) -> list[dict]:
        if not engine.url.get_backend_name().startswith("postgresql"):
            return []
        rows = self.db.execute(
            sql_text(
                "SELECT id, content FROM document_chunks "
                "WHERE embedding_vector IS NULL "
                "ORDER BY created_at, id "
                "LIMIT :limit"
            ),
            {"limit": limit},
        ).mappings()
        return [dict(row) for row in rows]

    def update_chunk_embedding_vector(self, chunk_id: str, embedding: list[float]) -> None:
        self.db.execute(
            sql_text(
                "UPDATE document_chunks "
                "SET embedding_vector = CAST(:embedding AS vector), embedding = CAST(:embedding_json AS json) "
                "WHERE id = :chunk_id"
            ),
            {
                "chunk_id": chunk_id,
                "embedding": self._vector_literal(embedding),
                "embedding_json": json.dumps(embedding),
            },
        )

    def vector_search_chunks(
        self,
        query_embedding: list[float],
        entity_ids: Iterable[str] | None = None,
        limit: int = 80,
    ) -> list[dict]:
        if not engine.url.get_backend_name().startswith("postgresql"):
            return []
        ids = list(entity_ids or [])
        where = "c.embedding_vector IS NOT NULL"
        params = {"embedding": self._vector_literal(query_embedding), "limit": limit, "entity_ids": ids}
        if ids:
            where += " AND c.heritage_entity_id = ANY(:entity_ids)"
        rows = self.db.execute(
            sql_text(
                "SELECT c.id AS chunk_id, c.document_id, c.heritage_entity_id, c.content, "
                "d.title, d.source_type, d.source_trust_level, "
                "GREATEST(0, 1 - (c.embedding_vector <=> CAST(:embedding AS vector))) AS vector_score "
                "FROM document_chunks c "
                "JOIN heritage_documents d ON d.id = c.document_id "
                f"WHERE {where} "
                "ORDER BY c.embedding_vector <=> CAST(:embedding AS vector) "
                "LIMIT :limit"
            ),
            params,
        ).mappings()
        return [dict(row) for row in rows]

    def keyword_search_chunks(
        self,
        query: str,
        entity_ids: Iterable[str] | None = None,
        limit: int = 80,
    ) -> list[dict]:
        if not engine.url.get_backend_name().startswith("postgresql"):
            return []
        ids = list(entity_ids or [])
        where = "(to_tsvector('simple', c.content) @@ plainto_tsquery('simple', :query) OR d.title ILIKE :like_query)"
        params = {"query": query, "like_query": f"%{query}%", "limit": limit, "entity_ids": ids}
        if ids:
            where += " AND c.heritage_entity_id = ANY(:entity_ids)"
        rows = self.db.execute(
            sql_text(
                "SELECT c.id AS chunk_id, c.document_id, c.heritage_entity_id, c.content, "
                "d.title, d.source_type, d.source_trust_level, "
                "ts_rank_cd(to_tsvector('simple', c.content), plainto_tsquery('simple', :query)) AS keyword_score "
                "FROM document_chunks c "
                "JOIN heritage_documents d ON d.id = c.document_id "
                f"WHERE {where} "
                "ORDER BY keyword_score DESC, c.created_at DESC "
                "LIMIT :limit"
            ),
            params,
        ).mappings()
        return [dict(row) for row in rows]

    def list_images_for_entities(self, entity_ids: Iterable[str], limit: int = 6) -> list[HeritageImage]:
        ids = [entity_id for entity_id in entity_ids if entity_id]
        if not ids:
            return []
        stmt = (
            select(HeritageImage)
            .where(HeritageImage.heritage_entity_id.in_(ids))
            .order_by(HeritageImage.source_trust_level, HeritageImage.id)
            .limit(limit)
        )
        return list(self.db.scalars(stmt))

    def ingest_official_dataset(self, dataset: dict, chunk_size: int = 900) -> dict[str, int]:
        entity_count = 0
        alias_count = 0
        document_count = 0
        chunk_count = 0
        relation_count = 0
        image_count = 0

        for row in dataset.get("entities", []):
            entity_id = self._required(row, "id")
            self.db.merge(
                HeritageEntity(
                    id=entity_id,
                    official_name_ko=row.get("official_name_ko", ""),
                    official_name_en=row.get("official_name_en", ""),
                    official_name_zh=row.get("official_name_zh", ""),
                    official_name_ja=row.get("official_name_ja", ""),
                    hanja_name=row.get("hanja_name") or None,
                    category=row.get("category", ""),
                    period=row.get("period", ""),
                    location_name=row.get("location_name", ""),
                    latitude=self._optional_float(row.get("latitude")),
                    longitude=self._optional_float(row.get("longitude")),
                    description=row.get("description", ""),
                    source_trust_level=row.get("source_trust_level", "S1"),
                )
            )
            entity_count += 1
        self.db.flush()

        for idx, row in enumerate(dataset.get("aliases", [])):
            alias = self._required(row, "alias")
            entity_id = self._required(row, "heritage_entity_id")
            alias_id = row.get("id") or f"{entity_id}-official-alias-{idx}"
            self.db.merge(
                HeritageAlias(
                    id=alias_id,
                    heritage_entity_id=entity_id,
                    alias=alias,
                    alias_normalized=row.get("alias_normalized") or normalize_key(alias),
                    language=row.get("language", "ko"),
                    alias_type=row.get("alias_type", "official"),
                    confidence_prior=self._optional_float(row.get("confidence_prior"), 1.0) or 1.0,
                )
            )
            alias_count += 1

        for idx, row in enumerate(dataset.get("documents", [])):
            content = self._required(row, "content")
            doc_id = row.get("id") or f"official-doc-{idx}"
            entity_id = row.get("heritage_entity_id") or None
            self.db.merge(
                HeritageDocument(
                    id=doc_id,
                    heritage_entity_id=entity_id,
                    title=row.get("title", doc_id),
                    source_type=row.get("source_type", "official_db"),
                    source_trust_level=row.get("source_trust_level", "S1"),
                    language=row.get("language", "ko"),
                    original_uri=row.get("original_uri") or None,
                    content=content,
                    doc_metadata=self._jsonish(row.get("metadata")),
                )
            )
            document_count += 1
            for chunk_index, chunk_content in enumerate(self._chunk_text(content, chunk_size)):
                chunk_hash = sha256(chunk_content.encode("utf-8")).hexdigest()
                chunk_id = f"{doc_id}-chunk-{chunk_index}"
                self.db.merge(
                    DocumentChunk(
                        id=chunk_id,
                        document_id=doc_id,
                        heritage_entity_id=entity_id,
                        chunk_index=chunk_index,
                        content=chunk_content,
                        content_hash=chunk_hash,
                        token_count=len(chunk_content.split()),
                        embedding=None,
                        chunk_metadata={"source": "official_ingest"},
                    )
                )
                chunk_count += 1

        relation_ids = count()
        for row in dataset.get("relations", []):
            source_id = self._required(row, "source_entity_id")
            target_id = self._required(row, "target_entity_id")
            relation_id = row.get("id") or f"official-relation-{next(relation_ids)}"
            self.db.merge(
                HeritageRelation(
                    id=relation_id,
                    source_entity_id=source_id,
                    target_entity_id=target_id,
                    relation_type=row.get("relation_type", "related_function"),
                    description=row.get("description", ""),
                    weight=self._optional_float(row.get("weight"), 1.0) or 1.0,
                )
            )
            relation_count += 1

        for row in dataset.get("images", []):
            entity_id = self._required(row, "heritage_entity_id")
            image_url = self._required(row, "image_url")
            image_id = row.get("id") or f"official-image-{sha256(f'{entity_id}:{image_url}'.encode('utf-8')).hexdigest()[:16]}"
            self.db.merge(
                HeritageImage(
                    id=image_id,
                    heritage_entity_id=entity_id,
                    document_id=row.get("document_id") or None,
                    title=row.get("title", ""),
                    image_url=image_url,
                    thumbnail_url=row.get("thumbnail_url") or None,
                    caption=row.get("caption", ""),
                    license_type=row.get("license_type", ""),
                    source_uri=row.get("source_uri") or None,
                    source_type=row.get("source_type", "official_image"),
                    source_trust_level=row.get("source_trust_level", "S1"),
                    image_metadata=self._jsonish(row.get("metadata")),
                )
            )
            image_count += 1

        self.db.commit()
        return {
            "entities": entity_count,
            "aliases": alias_count,
            "documents": document_count,
            "chunks": chunk_count,
            "relations": relation_count,
            "images": image_count,
        }

    def _chunk_text(self, text: str, chunk_size: int) -> list[str]:
        paragraphs = [part.strip() for part in text.split("\n") if part.strip()]
        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs or [text]:
            if len(current) + len(paragraph) + 1 <= chunk_size:
                current = f"{current}\n{paragraph}".strip()
            else:
                if current:
                    chunks.append(current)
                current = paragraph
        if current:
            chunks.append(current)
        return chunks or [text]

    def _required(self, row: dict, key: str) -> str:
        value = row.get(key)
        if value is None or str(value).strip() == "":
            raise ValueError(f"Missing required field: {key}")
        return str(value).strip()

    def _optional_float(self, value, default=None):
        if value is None or value == "":
            return default
        return float(value)

    def _jsonish(self, value):
        if not value:
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                import json

                return json.loads(value)
            except json.JSONDecodeError:
                return {"raw": value}
        return {"value": value}

    def _vector_literal(self, embedding: list[float]) -> str:
        return "[" + ",".join(f"{value:.8f}" for value in embedding) + "]"
