"""임베딩 호출 모듈 (RAG용).

Gemini ↔ OpenAI 교체가 환경변수로 가능하도록 추상화한다. SDK 의존성 없이
requests 기반 REST 호출만 사용한다.

진입점:
    embed_text(text) -> list[float]            # 단일 텍스트
    embed_texts([t1, t2, ...]) -> list[list]   # 여러 텍스트(배치)
    embed_dim() -> int                          # 현재 provider의 벡터 차원

provider 선택:
    환경변수 EMBED_PROVIDER ("gemini" | "openai"). 미설정 시 LLM_PROVIDER 를 따름.
    - Gemini : text-embedding-004 (768차원)
    - OpenAI : text-embedding-3-small (1536차원)
"""

from __future__ import annotations

import os
import time

import requests

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# EMBED_PROVIDER 미설정 시 LLM_PROVIDER 를 따른다.
EMBED_PROVIDER = os.getenv(
    "EMBED_PROVIDER", os.getenv("LLM_PROVIDER", "gemini")
).lower()

GEMINI_EMBED_MODEL = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001")
OPENAI_EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")

# gemini-embedding-001 은 출력 차원을 지정 가능(128~3072). 768로 고정해 pgvector 컬럼을 작게 유지.
GEMINI_EMBED_DIM = int(os.getenv("GEMINI_EMBED_DIM", "768"))

# OpenAI 모델별 고정 차원
_OPENAI_DIMS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
}

DEFAULT_TIMEOUT = 60


class EmbeddingError(Exception):
    """임베딩 호출 실패."""


def embed_dim() -> int:
    """현재 provider/모델의 벡터 차원을 반환한다."""
    if EMBED_PROVIDER == "gemini":
        return GEMINI_EMBED_DIM
    if EMBED_PROVIDER == "openai":
        return _OPENAI_DIMS.get(OPENAI_EMBED_MODEL, 1536)
    raise EmbeddingError(f"알 수 없는 EMBED_PROVIDER: {EMBED_PROVIDER}")


def embed_info() -> str:
    if EMBED_PROVIDER == "gemini":
        ok = bool(os.getenv("GEMINI_API_KEY"))
        return f"embed=gemini model={GEMINI_EMBED_MODEL} dim={embed_dim()} key={'OK' if ok else '없음'}"
    if EMBED_PROVIDER == "openai":
        ok = bool(os.getenv("OPENAI_API_KEY"))
        return f"embed=openai model={OPENAI_EMBED_MODEL} dim={embed_dim()} key={'OK' if ok else '없음'}"
    return f"embed=알수없음({EMBED_PROVIDER})"


# ── Gemini ───────────────────────────────────────────────
def _embed_gemini(texts: list[str], timeout: int) -> list[list[float]]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EmbeddingError("환경변수 GEMINI_API_KEY 가 설정되지 않았습니다.")

    model = GEMINI_EMBED_MODEL
    # gemini-embedding-001 은 sync batch(batchEmbedContents) 미지원 -> embedContent 단건 호출 반복.
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:embedContent"
    )
    vectors: list[list[float]] = []
    for t in texts:
        payload = {
            "model": f"models/{model}",
            "content": {"parts": [{"text": t}]},
            "outputDimensionality": GEMINI_EMBED_DIM,
        }
        data = _post_with_retry(url, {"key": api_key}, payload, timeout)
        try:
            vectors.append(data["embedding"]["values"])
        except (KeyError, TypeError) as exc:
            raise EmbeddingError(f"Gemini 임베딩 응답 파싱 실패: {data}") from exc
    return vectors


def _post_with_retry(url, params, payload, timeout, *, max_retry: int = 4) -> dict:
    """429/일시 오류 시 지수 백오프로 재시도. (인제스트 대량 호출 보호)"""
    delay = 2.0
    for attempt in range(max_retry + 1):
        try:
            resp = requests.post(url, params=params, json=payload, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status == 429 and attempt < max_retry:
                time.sleep(delay)
                delay *= 2
                continue
            body = getattr(exc.response, "text", "") if getattr(exc, "response", None) else ""
            raise EmbeddingError(f"Gemini 임베딩 실패: {exc} {body}") from exc


# ── OpenAI ───────────────────────────────────────────────
def _embed_openai(texts: list[str], timeout: int) -> list[list[float]]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EmbeddingError("환경변수 OPENAI_API_KEY 가 설정되지 않았습니다.")

    url = "https://api.openai.com/v1/embeddings"
    payload = {"model": OPENAI_EMBED_MODEL, "input": texts}
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        body = getattr(exc.response, "text", "") if getattr(exc, "response", None) else ""
        raise EmbeddingError(f"OpenAI 임베딩 실패: {exc} {body}") from exc

    data = resp.json()
    try:
        # index 순서 보장 위해 정렬
        items = sorted(data["data"], key=lambda d: d["index"])
        return [item["embedding"] for item in items]
    except (KeyError, TypeError) as exc:
        raise EmbeddingError(f"OpenAI 임베딩 응답 파싱 실패: {data}") from exc


# ── 통합 진입점 ──────────────────────────────────────────
def embed_texts(texts: list[str], *, timeout: int = DEFAULT_TIMEOUT) -> list[list[float]]:
    """여러 텍스트를 임베딩한다. (현재 provider 사용)"""
    if not texts:
        return []
    if EMBED_PROVIDER == "gemini":
        return _embed_gemini(texts, timeout)
    if EMBED_PROVIDER == "openai":
        return _embed_openai(texts, timeout)
    raise EmbeddingError(f"알 수 없는 EMBED_PROVIDER: {EMBED_PROVIDER}")


def embed_text(text: str, *, timeout: int = DEFAULT_TIMEOUT) -> list[float]:
    """단일 텍스트를 임베딩한다."""
    return embed_texts([text], timeout=timeout)[0]


if __name__ == "__main__":
    print(f"[임베딩 설정] {embed_info()}")
    vecs = embed_texts(["숭례문은 조선시대 한양도성의 정문이다.", "백자는 조선의 도자기다."])
    print(f"임베딩 개수: {len(vecs)}, 차원: {len(vecs[0])}")
    print(f"첫 벡터 앞 5개: {vecs[0][:5]}")
