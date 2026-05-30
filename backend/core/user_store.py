"""사용자 관심사 저장소 (경량 개인화).

익명 user_id(클라이언트 localStorage 생성) 기준으로 관심 카테고리 가중치를 누적한다.
로그인/인증 없이, 검색된 유산 청크의 카테고리(bcodeName)로 자동 학습한다.

테이블
  users(id, created_at)
  user_interests(user_id, category, weight)   -- 예: ('종교신앙', 4.0)

pgvector와 동일한 PostgreSQL 연결을 공유한다.
"""

from __future__ import annotations

from core.vector_store import get_conn

_schema_ready = False


def ensure_user_schema() -> None:
    """사용자/관심사 테이블을 보장한다 (최초 1회)."""
    global _schema_ready
    if _schema_ready:
        return
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id         TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT now()
            );
            CREATE TABLE IF NOT EXISTS user_interests (
                user_id  TEXT REFERENCES users(id) ON DELETE CASCADE,
                category TEXT,
                weight   REAL DEFAULT 0,
                PRIMARY KEY (user_id, category)
            );
            """
        )
    _schema_ready = True


def bump_interests(user_id: str, categories: list[str], by: float = 1.0) -> None:
    """주어진 카테고리들의 가중치를 누적한다 (없으면 생성).

    같은 카테고리가 여러 번 들어오면 횟수만큼 더해진다.
    """
    if not user_id or not categories:
        return
    ensure_user_schema()
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users(id) VALUES (%s) ON CONFLICT (id) DO NOTHING;",
            (user_id,),
        )
        for cat in categories:
            if not cat:
                continue
            cur.execute(
                """
                INSERT INTO user_interests(user_id, category, weight)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, category)
                DO UPDATE SET weight = user_interests.weight + EXCLUDED.weight;
                """,
                (user_id, cat, by),
            )


def top_interests(user_id: str, n: int = 3) -> list[tuple[str, float]]:
    """가중치 상위 관심 카테고리 목록을 반환한다."""
    if not user_id:
        return []
    ensure_user_schema()
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT category, weight FROM user_interests "
            "WHERE user_id=%s ORDER BY weight DESC, category LIMIT %s;",
            (user_id, n),
        )
        return [(r[0], float(r[1])) for r in cur.fetchall()]
