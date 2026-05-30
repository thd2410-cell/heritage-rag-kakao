"""요청 로그 저장소 (정량 평가용).

RAG 요청별 토큰·지연·캐시·모델을 pgvector와 동일한 PostgreSQL에 기록한다.
별도 인프라 없이 request_logs 테이블만 추가한다.
"""

from __future__ import annotations

from typing import Optional

from core.vector_store import get_conn

_ready = False


def ensure_schema() -> None:
    global _ready
    if _ready:
        return
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS request_logs (
                id            SERIAL PRIMARY KEY,
                ts            TIMESTAMP DEFAULT now(),
                endpoint      TEXT,
                question      TEXT,
                lang          TEXT,
                user_id       TEXT,
                multiturn     BOOLEAN,
                condensed     BOOLEAN,
                cached        BOOLEAN,
                answer_model  TEXT,
                llm_calls     INT,
                input_tokens  INT,
                output_tokens INT,
                total_tokens  INT,
                latency_ms    INT,
                num_sources   INT
            );
            """
        )
    _ready = True


def log(rec: dict) -> None:
    """요청 1건을 기록한다. 실패해도 본 요청에 영향 주지 않도록 호출부에서 감싼다."""
    ensure_schema()
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO request_logs
                (endpoint, question, lang, user_id, multiturn, condensed, cached,
                 answer_model, llm_calls, input_tokens, output_tokens, total_tokens,
                 latency_ms, num_sources)
            VALUES (%(endpoint)s, %(question)s, %(lang)s, %(user_id)s, %(multiturn)s,
                    %(condensed)s, %(cached)s, %(answer_model)s, %(llm_calls)s,
                    %(input_tokens)s, %(output_tokens)s, %(total_tokens)s,
                    %(latency_ms)s, %(num_sources)s);
            """,
            {
                "endpoint": rec.get("endpoint", "/api/rag"),
                "question": (rec.get("question") or "")[:200],
                "lang": rec.get("lang"),
                "user_id": rec.get("user_id"),
                "multiturn": rec.get("multiturn", False),
                "condensed": rec.get("condensed", False),
                "cached": rec.get("cached", False),
                "answer_model": rec.get("answer_model"),
                "llm_calls": rec.get("llm_calls", 0),
                "input_tokens": rec.get("input_tokens", 0),
                "output_tokens": rec.get("output_tokens", 0),
                "total_tokens": rec.get("total_tokens", 0),
                "latency_ms": rec.get("latency_ms", 0),
                "num_sources": rec.get("num_sources", 0),
            },
        )


def stats(endpoint: Optional[str] = None) -> dict:
    """집계 통계 — '얼마나 개선했는지' 증명용.

    캐시/비캐시, 모델별 평균 토큰·지연을 나눠 보여준다.
    """
    ensure_schema()
    conn = get_conn()
    where = "WHERE endpoint=%s" if endpoint else ""
    params = (endpoint,) if endpoint else ()
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM request_logs {where};", params)
        total = cur.fetchone()[0]

        # 캐시 여부별 평균
        cur.execute(
            f"""
            SELECT cached,
                   COUNT(*),
                   ROUND(AVG(total_tokens))::int,
                   ROUND(AVG(latency_ms))::int,
                   ROUND(AVG(llm_calls), 2)
            FROM request_logs {where}
            GROUP BY cached;
            """,
            params,
        )
        by_cached = {
            ("hit" if r[0] else "miss"): {
                "count": r[1],
                "avg_total_tokens": r[2],
                "avg_latency_ms": r[3],
                "avg_llm_calls": float(r[4]) if r[4] is not None else 0.0,
            }
            for r in cur.fetchall()
        }

        # 답변 모델별 (비캐시만 의미 있음)
        cur.execute(
            f"""
            SELECT answer_model, COUNT(*),
                   ROUND(AVG(total_tokens))::int, ROUND(AVG(latency_ms))::int
            FROM request_logs
            {where + (' AND' if where else 'WHERE')} cached = false AND answer_model IS NOT NULL
            GROUP BY answer_model;
            """,
            params,
        )
        by_model = {
            r[0]: {"count": r[1], "avg_total_tokens": r[2], "avg_latency_ms": r[3]}
            for r in cur.fetchall()
        }

    hits = by_cached.get("hit", {}).get("count", 0)
    return {
        "total_requests": total,
        "cache_hit_rate": round(hits / total, 3) if total else 0.0,
        "by_cached": by_cached,
        "by_answer_model": by_model,
    }
