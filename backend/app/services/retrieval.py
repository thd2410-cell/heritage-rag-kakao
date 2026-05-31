import re
from difflib import SequenceMatcher
from sqlalchemy import case, or_, text
from sqlalchemy.orm import Session
from app.models.heritage import Heritage
from app.services.embedding import embed_text

STOPWORDS = {
    "대해", "대한", "설명", "설명해줘", "쉽게", "심화", "자세", "알려줘", "해줘", "뭐야", "무엇", "퀴즈", "추천",
    "국가유산", "문화재", "문화유산", "유적", "유물",
}
PARTICLE_SUFFIXES = ("으로", "에서", "에게", "에는", "에는", "부터", "까지", "처럼", "보다", "하고", "이랑", "와", "과", "은", "는", "이", "가", "을", "를", "에", "의", "도")

COMMON_NAME_ALIASES = {
    "술래문": "숭례문",
    "남대문": "숭례문",
    "동대문": "흥인지문",
}


def apply_common_aliases(query: str) -> str:
    normalized = query or ""
    for wrong, right in COMMON_NAME_ALIASES.items():
        if wrong in normalized:
            normalized = normalized.replace(wrong, right)
    return normalized


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
                h.latitude,
                h.longitude,
                h.source_url,
                h.facet_json,
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


def normalize_term(term: str) -> str:
    for suffix in PARTICLE_SUFFIXES:
        if term.endswith(suffix) and len(term) > len(suffix) + 1:
            return term[: -len(suffix)]
    return term


def extract_search_terms(query: str) -> list[str]:
    raw_terms = re.findall(r"[가-힣A-Za-z0-9]{2,}", query or "")
    terms = [normalize_term(t) for t in raw_terms]
    terms = [t for t in terms if len(t) >= 2 and t not in STOPWORDS]
    # Prefer longer, more specific terms first while preserving uniqueness.
    return sorted(set(terms), key=lambda x: (-len(x), x))[:5]


def search_heritages_by_text(db: Session, query: str, limit: int = 3) -> list[dict]:
    terms = extract_search_terms(query)
    if not terms:
        return []
    conditions = []
    for term in terms:
        conditions.extend([Heritage.name.ilike(f"%{term}%"), Heritage.content.ilike(f"%{term}%")])
    first_term = terms[0]
    rank = case(
        (Heritage.name == first_term, 0),
        (Heritage.name.ilike(f"%{first_term}%"), 1),
        else_=2,
    )
    rows = (
        db.query(Heritage)
        .filter(or_(*conditions))
        .order_by(rank, Heritage.id.asc())
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
            "latitude": row.latitude,
            "longitude": row.longitude,
            "source_url": row.source_url,
            "facet_json": row.facet_json,
            "score": None,
        }
        for row in rows
    ]


def normalize_name_for_match(text: str) -> str:
    return re.sub(r"[^가-힣A-Za-z0-9]", "", text or "").lower()


def best_window_score(name: str, term: str) -> float:
    name_norm = normalize_name_for_match(name)
    term_norm = normalize_name_for_match(term)
    if not name_norm or not term_norm:
        return 0.0
    if term_norm in name_norm:
        return 1.0
    sizes = {len(term_norm), len(term_norm) + 1, max(1, len(term_norm) - 1)}
    best = SequenceMatcher(None, name_norm, term_norm).ratio()
    for size in sizes:
        if size > len(name_norm):
            continue
        for start in range(0, len(name_norm) - size + 1):
            best = max(best, SequenceMatcher(None, name_norm[start : start + size], term_norm).ratio())
    return best


def search_heritages_by_fuzzy_name(db: Session, query: str, limit: int = 3) -> list[dict]:
    terms = extract_search_terms(query)
    if not terms:
        return []
    candidates = db.query(Heritage).with_entities(
        Heritage.id,
        Heritage.name,
        Heritage.category,
        Heritage.region,
        Heritage.era,
        Heritage.address,
        Heritage.latitude,
        Heritage.longitude,
        Heritage.source_url,
        Heritage.content,
        Heritage.facet_json,
    ).all()
    ranked = []
    for row in candidates:
        score = max(best_window_score(row.name, term) for term in terms)
        if score >= 0.62:
            ranked.append((score, row))
    ranked.sort(key=lambda item: (-item[0], len(item[1].name or "")))
    return [
        {
            "chunk_id": None,
            "chunk_text": row.content or row.name,
            "metadata_json": {"fallback": "fuzzy_name", "fuzzy_score": score},
            "heritage_id": row.id,
            "name": row.name,
            "category": row.category,
            "region": row.region,
            "era": row.era,
            "address": row.address,
            "latitude": row.latitude,
            "longitude": row.longitude,
            "source_url": row.source_url,
            "facet_json": row.facet_json,
            "score": score,
        }
        for score, row in ranked[:limit]
    ]


def attach_nearby_heritages(db: Session, contexts: list[dict], limit: int = 5) -> list[dict]:
    for context in contexts:
        lat = context.get("latitude")
        lon = context.get("longitude")
        facet_json = dict(context.get("facet_json") or {})
        travel = dict(facet_json.get("travel_visit") or {})
        nearby: list[dict] = []
        if lat is not None and lon is not None:
            rows = db.execute(
                text(
                    """
                    SELECT
                        id,
                        name,
                        category,
                        region,
                        address,
                        latitude,
                        longitude,
                        6371 * acos(
                            least(1, greatest(-1,
                                cos(radians(:lat)) * cos(radians(latitude)) * cos(radians(longitude) - radians(:lon))
                                + sin(radians(:lat)) * sin(radians(latitude))
                            ))
                        ) AS distance_km
                    FROM heritages
                    WHERE id <> :heritage_id
                      AND latitude IS NOT NULL
                      AND longitude IS NOT NULL
                    ORDER BY distance_km ASC
                    LIMIT :limit
                    """
                ),
                {"lat": lat, "lon": lon, "heritage_id": context.get("heritage_id"), "limit": limit},
            ).mappings().all()
            nearby = [
                {
                    "name": row["name"],
                    "distance_km": round(float(row["distance_km"]), 1),
                    "category": row["category"],
                    "region": row["region"],
                    "address": row["address"],
                }
                for row in rows
            ]
        travel["nearby_heritages"] = nearby
        facet_json["travel_visit"] = travel
        context["facet_json"] = facet_json
    return contexts


def search_chunks(db: Session, query: str, limit: int = 3) -> list[dict]:
    query = apply_common_aliases(query)
    try:
        results = search_chunks_by_vector(db, query, limit=limit)
        if results:
            return attach_nearby_heritages(db, results)
    except RuntimeError:
        pass
    text_results = search_heritages_by_text(db, query, limit=limit)
    if text_results:
        return attach_nearby_heritages(db, text_results)
    return attach_nearby_heritages(db, search_heritages_by_fuzzy_name(db, query, limit=limit))
