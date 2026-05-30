"""pgvector 벡터 스토어.

PostgreSQL + pgvector 에 국가유산 원문 청크와 용어 사전을 임베딩과 함께 저장하고,
코사인 유사도로 검색한다.

테이블: heritage_chunks
  id, source_type('heritage'|'term'), heritage_name, term, chunk_index, content, embedding

연결 정보는 환경변수(PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE)에서 읽는다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import psycopg2
from pgvector.psycopg2 import register_vector

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

TABLE = "heritage_chunks"

_conn = None  # 모듈 수준 캐시 연결


@dataclass
class SearchHit:
    """검색 결과 1건."""

    content: str
    source_type: str          # 'heritage' | 'term'
    heritage_name: Optional[str]
    term: Optional[str]
    similarity: float         # 1 - cosine_distance (1에 가까울수록 유사)
    image_url: Optional[str] = None
    category: Optional[str] = None  # 유산 분류(bcodeName) — 개인화 가중치용


def _connect():
    return psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PGPORT", "5432")),
        user=os.getenv("PGUSER", "heritage"),
        password=os.getenv("PGPASSWORD", "heritage"),
        dbname=os.getenv("PGDATABASE", "heritage"),
    )


def get_conn():
    """autocommit + vector 등록된 연결을 반환한다(캐시)."""
    global _conn
    if _conn is not None and _conn.closed == 0:
        return _conn
    conn = _connect()
    conn.autocommit = True
    # vector 익스텐션 보장 후 타입 등록
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    register_vector(conn)
    _conn = conn
    return conn


def ensure_schema(dim: int) -> None:
    """테이블이 없으면 생성한다."""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {TABLE} (
                id            SERIAL PRIMARY KEY,
                source_type   TEXT NOT NULL,
                heritage_name TEXT,
                term          TEXT,
                chunk_index   INT,
                content       TEXT NOT NULL,
                image_url     TEXT,
                category      TEXT,
                embedding     vector({dim}) NOT NULL
            );
            """
        )
        # 기존 테이블 마이그레이션
        cur.execute(f"ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS image_url TEXT;")
        cur.execute(f"ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS category TEXT;")


def reset_schema(dim: int) -> None:
    """테이블을 DROP 후 재생성한다 (재적재용). 차원 변경 시에도 안전."""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS {TABLE};")
    ensure_schema(dim)


def insert_chunks(records: list[dict]) -> int:
    """청크 레코드를 일괄 삽입한다.

    각 record: {source_type, heritage_name, term, chunk_index, content, embedding}
    """
    if not records:
        return 0
    for rec in records:
        rec.setdefault("image_url", None)
        rec.setdefault("category", None)
    conn = get_conn()
    with conn.cursor() as cur:
        cur.executemany(
            f"""
            INSERT INTO {TABLE}
                (source_type, heritage_name, term, chunk_index, content, image_url, category, embedding)
            VALUES (%(source_type)s, %(heritage_name)s, %(term)s,
                    %(chunk_index)s, %(content)s, %(image_url)s, %(category)s, %(embedding)s);
            """,
            records,
        )
    return len(records)


def _rows_to_hits(rows) -> list[SearchHit]:
    # 컬럼 순서: content, source_type, heritage_name, term, image_url, category, similarity
    return [
        SearchHit(
            content=r[0],
            source_type=r[1],
            heritage_name=r[2],
            term=r[3],
            image_url=r[4],
            category=r[5],
            similarity=float(r[6]) if r[6] is not None else 0.0,
        )
        for r in rows
    ]


def search(
    query_embedding, top_k: int = 5, *, heritage_name: Optional[str] = None
) -> list[SearchHit]:
    """질문 임베딩과 코사인 유사도가 높은 청크 top_k 개를 반환한다.

    pgvector 의 <=> 연산자는 코사인 '거리'(0=동일). 유사도 = 1 - 거리.
    heritage_name 을 주면 해당 유산의 청크로만 한정 검색한다(이름 필터).
    """
    conn = get_conn()
    where = ""
    params: list = [query_embedding]
    if heritage_name:
        where = "WHERE heritage_name = %s"
        params.append(heritage_name)
    params += [query_embedding, top_k]
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT content, source_type, heritage_name, term, image_url, category,
                   1 - (embedding <=> %s::vector) AS similarity
            FROM {TABLE}
            {where}
            ORDER BY embedding <=> %s::vector
            LIMIT %s;
            """,
            params,
        )
        return _rows_to_hits(cur.fetchall())


# 키워드 검색에서 제외할 흔한 단어(이게 용어 정의 본문에 걸려 노이즈를 만든다)
_KEYWORD_STOPWORDS = {
    "위해", "위한", "통해", "대해", "관해", "사용", "있는", "없는", "이다", "한다",
    "했다", "정보", "시대", "한국", "처럼", "모두", "그리고", "하지만", "라고", "라는",
    "에서", "으로", "이라고", "불렸", "알고", "있어", "있다", "정체성", "없애",
}


def keyword_search(tokens: list[str], limit: int = 5) -> list[SearchHit]:
    """유산명/용어명에 키워드가 ILIKE 매칭되는 청크를 반환한다(유사도 없음).

    본문(content) 매칭은 흔한 단어가 용어 정의에 걸려 노이즈를 만들므로 제외하고,
    식별성이 있는 유산명·용어명에만 매칭한다. 불용어도 거른다.
    """
    toks = [t for t in tokens if len(t) >= 2 and t not in _KEYWORD_STOPWORDS]
    if not toks:
        return []
    patterns = [f"%{t}%" for t in toks]
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT content, source_type, heritage_name, term, image_url, category, NULL
            FROM {TABLE}
            WHERE heritage_name ILIKE ANY(%s)
               OR term ILIKE ANY(%s)
            LIMIT %s;
            """,
            (patterns, patterns, limit),
        )
        return _rows_to_hits(cur.fetchall())


def heritage_image(name: str) -> Optional[str]:
    """해당 유산의 대표 이미지 URL을 반환한다(없으면 None)."""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT image_url FROM {TABLE} "
            f"WHERE heritage_name=%s AND image_url IS NOT NULL AND image_url<>'' LIMIT 1;",
            (name,),
        )
        row = cur.fetchone()
        return row[0] if row else None


def set_heritage_image(name: str, image_url: str) -> int:
    """유산명의 모든 청크에 image_url을 채운다(백필용). 갱신된 행 수 반환."""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE {TABLE} SET image_url=%s WHERE heritage_name=%s;",
            (image_url, name),
        )
        return cur.rowcount


def heritage_headers() -> list[tuple[str, str]]:
    """각 유산의 헤더 청크(chunk_index=0) (유산명, 본문)을 반환한다. (category 백필용)"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT heritage_name, content FROM {TABLE} "
            f"WHERE source_type='heritage' AND chunk_index=0;"
        )
        return [(r[0], r[1]) for r in cur.fetchall()]


def set_category(heritage_name: str, category: str) -> int:
    """유산명의 모든 청크에 category를 채운다. 갱신된 행 수 반환."""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE {TABLE} SET category=%s WHERE heritage_name=%s;",
            (category, heritage_name),
        )
        return cur.rowcount


def heritages_by_category(category: str, limit: int = 6) -> list[tuple[str, Optional[str]]]:
    """해당 분류(category)에 속한 유산 (유산명, 이미지URL) 목록을 반환한다. (추천용)"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT DISTINCT ON (heritage_name) heritage_name, image_url
            FROM {TABLE}
            WHERE source_type='heritage' AND category=%s AND heritage_name IS NOT NULL
            ORDER BY heritage_name
            LIMIT %s;
            """,
            (category, limit),
        )
        return [(r[0], r[1]) for r in cur.fetchall()]


def chunks_of(heritage_name: str) -> list[str]:
    """해당 유산의 본문 청크를 chunk_index 순서로 반환한다. (Q&A 생성용)"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT content FROM {TABLE} "
            f"WHERE source_type='heritage' AND heritage_name=%s "
            f"ORDER BY chunk_index;",
            (heritage_name,),
        )
        return [r[0] for r in cur.fetchall()]


def existing_heritage_names() -> set[str]:
    """이미 적재된 유산명 집합 (중복 적재 방지용)."""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT DISTINCT heritage_name FROM {TABLE} WHERE source_type='heritage';"
        )
        return {r[0] for r in cur.fetchall() if r[0]}


def delete_by_source_type(source_type: str) -> int:
    """특정 source_type 청크를 모두 삭제한다(재적재 idempotency). 삭제 행 수 반환."""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM {TABLE} WHERE source_type=%s;", (source_type,))
        return cur.rowcount


def count() -> int:
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {TABLE};")
        return cur.fetchone()[0]


def stats() -> dict:
    """저장 현황(유형별/유산별 청크 수)."""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT source_type, COUNT(*) FROM {TABLE} GROUP BY source_type;"
        )
        by_type = {r[0]: r[1] for r in cur.fetchall()}
        cur.execute(
            f"SELECT heritage_name, COUNT(*) FROM {TABLE} "
            f"WHERE source_type='heritage' GROUP BY heritage_name;"
        )
        by_heritage = {r[0]: r[1] for r in cur.fetchall()}
    return {"total": count(), "by_type": by_type, "by_heritage": by_heritage}


def ping() -> bool:
    """DB 연결 가능 여부."""
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
            cur.fetchone()
        return True
    except Exception:
        return False
