from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class HeritageEntity(Base):
    __tablename__ = "heritage_entities"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    official_name_ko: Mapped[str] = mapped_column(String, index=True)
    official_name_en: Mapped[str] = mapped_column(String, default="")
    official_name_zh: Mapped[str] = mapped_column(String, default="")
    official_name_ja: Mapped[str] = mapped_column(String, default="")
    hanja_name: Mapped[str | None] = mapped_column(String, nullable=True)
    category: Mapped[str] = mapped_column(String, default="")
    period: Mapped[str] = mapped_column(String, default="")
    location_name: Mapped[str] = mapped_column(String, default="")
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    source_trust_level: Mapped[str] = mapped_column(String, default="S1")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class HeritageAlias(Base):
    __tablename__ = "heritage_aliases"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    heritage_entity_id: Mapped[str] = mapped_column(ForeignKey("heritage_entities.id"), index=True)
    alias: Mapped[str] = mapped_column(String, index=True)
    alias_normalized: Mapped[str] = mapped_column(String, index=True)
    language: Mapped[str] = mapped_column(String)
    alias_type: Mapped[str] = mapped_column(String)
    confidence_prior: Mapped[float] = mapped_column(Float, default=1.0)


class HeritageDocument(Base):
    __tablename__ = "heritage_documents"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    heritage_entity_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    title: Mapped[str] = mapped_column(String)
    source_type: Mapped[str] = mapped_column(String)
    source_trust_level: Mapped[str] = mapped_column(String)
    language: Mapped[str] = mapped_column(String)
    original_uri: Mapped[str | None] = mapped_column(String, nullable=True)
    content: Mapped[str] = mapped_column(Text)
    doc_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    document_id: Mapped[str] = mapped_column(String, index=True)
    heritage_entity_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    chunk_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class HeritageRelation(Base):
    __tablename__ = "heritage_relations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    source_entity_id: Mapped[str] = mapped_column(String, index=True)
    target_entity_id: Mapped[str] = mapped_column(String, index=True)
    relation_type: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    weight: Mapped[float] = mapped_column(Float, default=1.0)


class HeritageImage(Base):
    __tablename__ = "heritage_images"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    heritage_entity_id: Mapped[str] = mapped_column(String, index=True)
    document_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    title: Mapped[str] = mapped_column(String, default="")
    image_url: Mapped[str] = mapped_column(Text)
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    caption: Mapped[str] = mapped_column(Text, default="")
    license_type: Mapped[str] = mapped_column(String, default="")
    source_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String, default="official_image")
    source_trust_level: Mapped[str] = mapped_column(String, default="S1")
    image_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
