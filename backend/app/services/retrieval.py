from sqlalchemy import or_, text
from sqlalchemy.orm import Session
from app.models.heritage import Heritage
from app.services.embedding import embed_text


def search_chunks_by_vector(db: Session, query: str, limit: int = 3) -> list[dict]:
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


def search_heritages_by_text(db: Session, query: str, limit: int = 3) -> list[dict]:
    keyword = query.strip()
    if not keyword:
        return []
    rows = (
        db.query(Heritage)
        .filter(or_(Heritage.name.ilike(f"%{keyword}%"), Heritage.content.ilike(f"%{keyword}%")))
        .order_by(Heritage.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "chunk_id": None,
            "chunk_text": row.content or row.name,
            "metadata_json": {"fallback": "text_search"},
            "heritage_id": row.id,
            "name": row.name,
            "category": row.category,
            "region": row.region,
            "era": row.era,
            "address": row.address,
            "source_url": row.source_url,
            "score": None,
        }
        for row in rows
    ]


def search_chunks(db: Session, query: str, limit: int = 3) -> list[dict]:
    try:
        results = search_chunks_by_vector(db, query, limit=limit)
        if results:
            return results
    except RuntimeError:
        pass
    return search_heritages_by_text(db, query, limit=limit)
