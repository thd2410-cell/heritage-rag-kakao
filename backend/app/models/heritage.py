from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector
from app.db.session import Base


class Heritage(Base):
    __tablename__ = "heritages"
    __table_args__ = (UniqueConstraint("ccba_kdcd", "ccba_asno", "ccba_ctcd"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ccba_kdcd: Mapped[str] = mapped_column(Text, nullable=False)
    ccba_asno: Mapped[str] = mapped_column(Text, nullable=False)
    ccba_ctcd: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(Text)
    region: Mapped[str | None] = mapped_column(Text)
    era: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    image_url: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[dict | None] = mapped_column(JSONB)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    chunks: Mapped[list["DocumentChunk"]] = relationship(back_populates="heritage", cascade="all, delete-orphan")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    heritage_id: Mapped[int] = mapped_column(ForeignKey("heritages.id", ondelete="CASCADE"), nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding = mapped_column(Vector(1024))
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    heritage: Mapped[Heritage] = relationship(back_populates="chunks")


class ChatLog(Base):
    __tablename__ = "chat_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_key: Mapped[str | None] = mapped_column(Text)
    utterance: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[dict | list | None] = mapped_column(JSONB)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
