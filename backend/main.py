"""국가유산 AI 해설사 — FastAPI 앱.

엔드포인트:
  GET /api/heritage?name=숭례문&lang=ko   -> 한국어 해설
  GET /api/heritage?name=숭례문&lang=en   -> 영어 번역
  GET /api/heritage?name=숭례문&lang=zh   -> 중국어 (Phase 2, 파라미터 개통)
  GET /api/heritage?name=숭례문&lang=ja   -> 일본어 (동일)

실행:
  backend/ 디렉터리에서
    uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from api.heritage_api import HeritageAPIError
from api.llm_api import LLMError, is_configured
from core.cache import SimpleCache
from core.pipeline import (
    answer_followup,
    expand_dictionary_from_content,
    rag_answer,
    run_pipeline_for_lang,
)

SUPPORTED_LANGS = {"ko", "en", "zh", "ja"}

# 유산 해설/번역 응답 캐시 (같은 name+lang 재조회 시 LLM 호출 절약)
# TTL 6시간: 원문이 자주 바뀌지 않으므로 충분히 길게.
heritage_cache = SimpleCache(maxsize=512, ttl=6 * 60 * 60)

# RAG 응답 캐시 (단일턴 질문 한정). 같은 질문+언어+관심프로필 재요청 시 LLM 호출 절약.
rag_cache = SimpleCache(maxsize=256, ttl=60 * 60)

app = FastAPI(
    title="국가유산 AI 해설사",
    description="국가유산청 Open API + LLM 기반 다국어 해설 챗봇",
    version="0.1.0",
)

# React 연결을 위해 CORS 개방 (개발용: 전체 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    """헬스 체크 + LLM 설정 상태 + 캐시 통계."""
    _, info = is_configured()
    return {
        "status": "ok",
        "service": "heritage-ai",
        "llm": info,
        "cache": heritage_cache.stats(),
    }


@app.get("/api/heritage")
def heritage(
    name: str = Query(..., description="유산 이름 (예: 숭례문)"),
    lang: str = Query("ko", description="ko | en | zh | ja"),
):
    """유산 이름과 언어로 해설/번역을 반환한다."""
    lang = (lang or "ko").lower()
    if lang not in SUPPORTED_LANGS:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 언어: '{lang}' (가능: {', '.join(sorted(SUPPORTED_LANGS))})",
        )
    if not name or not name.strip():
        raise HTTPException(status_code=400, detail="유산 이름(name)을 입력하세요.")

    # ── 캐시 조회 ──────────────────────────────────────
    cache_key = f"{name.strip()}|{lang}"
    cached = heritage_cache.get(cache_key)
    if cached is not None:
        return {**cached, "cached": True}

    try:
        result = run_pipeline_for_lang(name.strip(), lang)
    except HeritageAPIError as exc:
        raise HTTPException(status_code=502, detail=f"국가유산청 API 오류: {exc}")
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=f"LLM 호출 오류: {exc}")

    if not result.found:
        raise HTTPException(status_code=404, detail=result.message)

    # 명세 응답 형태 (+ content: 후속 질문 grounding용 한국어 원문)
    payload = {
        "name": result.name,
        "hanja": result.name_hanja,
        "period": result.era,
        "imageUrl": result.image_url,
        "explanation": result.explanation,
        "lang": result.lang,
        "detected_terms": result.detected_terms,
        "content": result.source_content,
        "note": result.note,
    }
    # LLM 해설이 실제로 생성된 경우에만 캐싱 (미설정 fallback은 캐싱하지 않음)
    if is_configured()[0]:
        heritage_cache.set(cache_key, payload)
    return {**payload, "cached": False}


class AskTurn(BaseModel):
    q: str = ""
    a: str = ""


class AskRequest(BaseModel):
    name: str = Field(..., description="현재 유산 한글 명칭")
    content: str = Field(..., description="grounding 원문 (한국어, /api/heritage 응답의 content)")
    question: str = Field(..., description="후속 질문")
    hanja: str = ""
    lang: str = "ko"
    history: list[AskTurn] = Field(default_factory=list)


@app.post("/api/ask")
def ask(req: AskRequest):
    """현재 유산에 대한 후속 질문에 원문 근거로 답한다. (대화 맥락 유지)"""
    lang = (req.lang or "ko").lower()
    if lang not in SUPPORTED_LANGS:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 언어: '{lang}'")
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="질문(question)을 입력하세요.")
    if not req.content.strip():
        raise HTTPException(
            status_code=400,
            detail="현재 유산 정보(content)가 없습니다. 먼저 유산을 검색하세요.",
        )

    try:
        answer = answer_followup(
            name=req.name,
            content=req.content,
            question=req.question.strip(),
            hanja=req.hanja,
            lang=lang,
            history=[t.model_dump() for t in req.history],
        )
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=f"LLM 호출 오류: {exc}")

    return {"answer": answer, "lang": lang}


class RagTurn(BaseModel):
    role: str = ""   # "user" | "bot"
    text: str = ""


class RagRequest(BaseModel):
    question: str = Field(..., description="자유 질문")
    lang: str = "ko"
    top_k: int = Field(5, ge=1, le=10, description="검색할 청크 수")
    history: list[RagTurn] = Field(default_factory=list, description="이전 대화 (멀티턴)")
    user_id: str = Field("", description="익명 사용자 ID (개인화)")


def _safe_log(rec: dict) -> None:
    """요청 로그 기록 — 실패해도 본 응답에 영향 주지 않는다."""
    try:
        from core import request_log

        request_log.log(rec)
    except Exception:
        pass


@app.get("/api/metrics")
def metrics():
    """정량 평가 집계 (캐시/모델별 평균 토큰·지연, 캐시 적중률)."""
    try:
        from core import request_log

        return request_log.stats(endpoint="/api/rag")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"메트릭 조회 오류: {exc}")


@app.post("/api/rag")
def rag(req: RagRequest):
    """질문을 임베딩→pgvector 검색→상위 청크 근거로 답한다. (RAG)"""
    lang = (req.lang or "ko").lower()
    if lang not in SUPPORTED_LANGS:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 언어: '{lang}'")
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="질문(question)을 입력하세요.")

    # ── 캐시 조회 ──────────────────────────────────────
    #   단일턴(이력 없음) + 비개인화(관심사 없음) 요청만 캐싱한다.
    #   - 멀티턴: 맥락 의존이라 제외
    #   - 개인화 요청: 관심 프로필에 맞춰 답이 달라지므로 항상 새로 생성
    #   익명/신규 사용자의 같은 질문은 캐시 적중 → LLM 호출 절약.
    from core import user_store

    import time

    from api import llm_api
    from core import request_log

    interest_sig = ""
    if req.user_id:
        interest_sig = ",".join(c for c, _ in user_store.top_interests(req.user_id, 3))
    cacheable = (not req.history) and (interest_sig == "")
    cache_key = f"{lang}|{question}"

    t0 = time.perf_counter()
    if cacheable:
        hit = rag_cache.get(cache_key)
        if hit is not None:
            # 캐시 적중: LLM 호출 0, 즉시 응답 — 기록만 남긴다.
            latency_ms = int((time.perf_counter() - t0) * 1000)
            _safe_log(
                {
                    "endpoint": "/api/rag", "question": question, "lang": lang,
                    "user_id": req.user_id, "multiturn": False, "condensed": False,
                    "cached": True, "answer_model": None, "llm_calls": 0,
                    "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
                    "latency_ms": latency_ms,
                    "num_sources": len(hit.get("sources", [])),
                }
            )
            return {**hit, "cached": True, "meta": {"cached": True, "latency_ms": latency_ms, "total_tokens": 0}}

    try:
        with llm_api.Meter() as meter:
            result = rag_answer(
                question,
                lang=lang,
                top_k=req.top_k,
                history=[t.model_dump() for t in req.history],
                user_id=req.user_id or None,
            )
        usage = meter.totals()
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=f"LLM 호출 오류: {exc}")
    except Exception as exc:  # 임베딩/DB 오류
        raise HTTPException(status_code=502, detail=f"RAG 검색 오류: {exc}")

    latency_ms = int((time.perf_counter() - t0) * 1000)
    _safe_log(
        {
            "endpoint": "/api/rag", "question": question, "lang": lang,
            "user_id": req.user_id, "multiturn": bool(req.history),
            "condensed": result.meta.get("condensed", False), "cached": False,
            "answer_model": result.meta.get("answer_model"),
            "llm_calls": usage["llm_calls"], "input_tokens": usage["input_tokens"],
            "output_tokens": usage["output_tokens"], "total_tokens": usage["total_tokens"],
            "latency_ms": latency_ms, "num_sources": len(result.sources),
        }
    )

    payload = {
        "answer": result.answer,
        "lang": lang,
        "imageUrl": result.image_url,
        "imageName": result.image_name,
        "images": result.images,
        "sources": [
            {
                "label": s.label,
                "similarity": s.similarity,
                "snippet": s.snippet,
                "content": s.content,
                "refs": s.refs,
            }
            for s in result.sources
        ],
    }
    if cacheable:
        rag_cache.set(cache_key, payload)
    meta = {
        "cached": False,
        "latency_ms": latency_ms,
        "total_tokens": usage["total_tokens"],
        "llm_calls": usage["llm_calls"],
        "answer_model": result.meta.get("answer_model"),
        "condensed": result.meta.get("condensed", False),
    }
    return {**payload, "cached": False, "meta": meta}


@app.get("/api/me")
def me(user_id: str = Query(..., description="익명 사용자 ID")):
    """사용자의 학습된 관심 분야(가중치 순)를 반환한다."""
    from core import user_store

    interests = user_store.top_interests(user_id, n=5)
    return {
        "user_id": user_id,
        "interests": [{"category": c, "weight": round(w, 1)} for c, w in interests],
    }


@app.get("/api/recommend")
def recommend(
    user_id: str = Query(..., description="익명 사용자 ID"),
    n: int = Query(3, ge=1, le=8),
):
    """사용자의 최상위 관심 분야에 속한 유산을 추천한다."""
    from core import user_store, vector_store

    interests = user_store.top_interests(user_id, n=1)
    if not interests:
        return {"category": "", "items": []}  # 아직 학습 전

    category = interests[0][0]
    rows = vector_store.heritages_by_category(category, limit=n * 2)
    items = [{"name": name, "imageUrl": url} for name, url in rows if url][:n]
    return {"category": category, "items": items}


class ExpandRequest(BaseModel):
    content: str = Field(..., description="용어를 추출·정의할 해설 원문")
    max_new: int = Field(5, ge=1, le=20, description="한 번에 등록할 최대 신규 용어 수")


@app.post("/api/expand-terms")
def expand_terms(req: ExpandRequest):
    """원문에서 사전에 없는 전문 용어를 찾아 LLM 정의를 생성·등록한다."""
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="원문(content)을 입력하세요.")
    try:
        added = expand_dictionary_from_content(req.content, max_new=req.max_new)
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=f"LLM 호출 오류: {exc}")

    # 새 용어가 추가되면 기존 해설 캐시는 낡은 것이므로 비운다.
    if added:
        heritage_cache.clear()
        rag_cache.clear()

    return {
        "added": [
            {"term": a.term, "hanja": a.hanja, "definition": a.definition}
            for a in added
        ],
        "added_count": len(added),
    }
