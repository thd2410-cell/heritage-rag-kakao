from sqlalchemy import text
from sqlalchemy.orm import Session
from app.services.embedding import embed_text


def search_chunks(db: Session, query: str, limit: int = 3) -> list[dict]:
    qvec = "[" + ",".join(str(x) for x in embed_text(query)) + "]"
    rows = db.execute(
        text(
            """
            SELECT
                dc.id AS chunk_id,
                dc.chunk_text,
                dc.metadata_json,
                h.id AS heritage_id,
                h.name,
                h.category,
                h.region,
                h.era,
                h.address,
                h.source_url,
                1 - (dc.embedding <=> CAST(:qvec AS vector)) AS score
            FROM document_chunks dc
            JOIN heritages h ON h.id = dc.heritage_id
            WHERE dc.embedding IS NOT NULL
            ORDER BY dc.embedding <=> CAST(:qvec AS vector)
            LIMIT :limit
            """
        ),
        {"qvec": qvec, "limit": limit},
    ).mappings().all()
    return [dict(row) for row in rows]
