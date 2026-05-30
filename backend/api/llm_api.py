"""LLM 호출 모듈 (파이프라인 4~5단계 엔진).

Gemini ↔ OpenAI 교체가 환경변수 한 줄로 가능하도록 추상화한다.
SDK 의존성 없이 requests 기반 REST 호출만 사용한다.

진입점:
    call_llm(system_prompt, user_message) -> str

provider 선택:
    환경변수 LLM_PROVIDER = "gemini"(기본) | "openai"
    - Gemini : 환경변수 GEMINI_API_KEY,  모델 GEMINI_MODEL (기본 gemini-2.5-flash)
    - OpenAI : 환경변수 OPENAI_API_KEY,  모델 OPENAI_MODEL (기본 gpt-4.1)
"""

from __future__ import annotations

import os

import requests

try:
    # .env 파일이 있으면 자동 로드 (선택적 의존성)
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# "gemini" 또는 "openai" 로 변경하면 전체 LLM 백엔드가 교체된다.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1")

# 단순 보조 작업(질의 재작성 등)용 저렴한 모델
GEMINI_CONDENSE_MODEL = os.getenv("GEMINI_CONDENSE_MODEL", "gemini-2.5-flash-lite")
OPENAI_CONDENSE_MODEL = os.getenv("OPENAI_CONDENSE_MODEL", "gpt-4.1-mini")

DEFAULT_TIMEOUT = 60


class LLMError(Exception):
    """LLM 호출 실패 (키 없음/네트워크/응답 형식 오류)."""


# ── 토큰 사용량 계측 (정량 평가용) ───────────────────────
import threading  # noqa: E402

_meter_local = threading.local()


def _record_usage(provider: str, model: str, input_tokens, output_tokens) -> None:
    """현재 활성화된 Meter 가 있으면 LLM 호출 사용량을 기록한다."""
    bucket = getattr(_meter_local, "bucket", None)
    if bucket is not None:
        bucket.append(
            {
                "provider": provider,
                "model": model,
                "input_tokens": int(input_tokens or 0),
                "output_tokens": int(output_tokens or 0),
            }
        )


class Meter:
    """with 블록 동안의 LLM 토큰 사용량을 누적한다.

        with Meter() as m:
            ... LLM 호출들 ...
        m.totals()  # {llm_calls, input_tokens, output_tokens, total_tokens, models}
    """

    def __enter__(self):
        _meter_local.bucket = []
        return self

    def __exit__(self, *exc):
        self.records = getattr(_meter_local, "bucket", []) or []
        _meter_local.bucket = None
        return False

    def totals(self) -> dict:
        recs = getattr(self, "records", [])
        inp = sum(r["input_tokens"] for r in recs)
        out = sum(r["output_tokens"] for r in recs)
        return {
            "llm_calls": len(recs),
            "input_tokens": inp,
            "output_tokens": out,
            "total_tokens": inp + out,
            "models": [r["model"] for r in recs],
        }


# ── Gemini ───────────────────────────────────────────────
def call_gemini(
    system_prompt: str,
    user_message: str,
    *,
    model: str | None = None,
    temperature: float = 0.4,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise LLMError("환경변수 GEMINI_API_KEY 가 설정되지 않았습니다.")

    model = model or GEMINI_MODEL
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    payload = {
        # 시스템 지시는 systemInstruction 으로 분리 전달
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_message}]}],
        "generationConfig": {"temperature": temperature},
    }
    try:
        resp = requests.post(
            url,
            params={"key": api_key},
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        # 응답 본문이 있으면 오류 메시지에 포함
        body = getattr(exc.response, "text", "") if getattr(exc, "response", None) else ""
        raise LLMError(f"Gemini 호출 실패: {exc} {body}") from exc

    data = resp.json()
    um = data.get("usageMetadata") or {}
    _record_usage(
        "gemini", model, um.get("promptTokenCount"), um.get("candidatesTokenCount")
    )
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError) as exc:
        raise LLMError(f"Gemini 응답 파싱 실패: {data}") from exc


# ── OpenAI ───────────────────────────────────────────────
def call_openai(
    system_prompt: str,
    user_message: str,
    *,
    model: str | None = None,
    temperature: float = 0.4,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise LLMError("환경변수 OPENAI_API_KEY 가 설정되지 않았습니다.")

    model = model or OPENAI_MODEL
    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": temperature,
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        body = getattr(exc.response, "text", "") if getattr(exc, "response", None) else ""
        raise LLMError(f"OpenAI 호출 실패: {exc} {body}") from exc

    data = resp.json()
    um = data.get("usage") or {}
    _record_usage(
        "openai", model, um.get("prompt_tokens"), um.get("completion_tokens")
    )
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as exc:
        raise LLMError(f"OpenAI 응답 파싱 실패: {data}") from exc


# ── 통합 진입점 ──────────────────────────────────────────
def light_model() -> str:
    """현재 provider의 '저렴한 보조 모델' 이름을 반환한다(질의 재작성 등)."""
    return GEMINI_CONDENSE_MODEL if LLM_PROVIDER == "gemini" else OPENAI_CONDENSE_MODEL


def default_model() -> str:
    """현재 provider의 기본(full) 모델 이름을 반환한다."""
    return GEMINI_MODEL if LLM_PROVIDER == "gemini" else OPENAI_MODEL


def call_llm(
    system_prompt: str,
    user_message: str,
    *,
    temperature: float = 0.4,
    timeout: int = DEFAULT_TIMEOUT,
    model: str | None = None,
) -> str:
    """현재 설정된 provider로 LLM을 호출한다.

    LLM_PROVIDER 환경변수("gemini" | "openai")로 백엔드가 결정된다.
    model 을 주면 해당 모델로 호출한다(예: 보조 작업에 저렴한 모델).
    """
    if LLM_PROVIDER == "gemini":
        return call_gemini(
            system_prompt, user_message, model=model, temperature=temperature, timeout=timeout
        )
    elif LLM_PROVIDER == "openai":
        return call_openai(
            system_prompt, user_message, model=model, temperature=temperature, timeout=timeout
        )
    raise LLMError(
        f"알 수 없는 LLM_PROVIDER: '{LLM_PROVIDER}' (gemini 또는 openai 사용)"
    )


def is_configured() -> tuple[bool, str]:
    """현재 provider의 API 키가 설정됐는지 확인한다. (provider, 안내메시지)"""
    if LLM_PROVIDER == "gemini":
        ok = bool(os.getenv("GEMINI_API_KEY"))
        return ok, f"provider=gemini model={GEMINI_MODEL} key={'OK' if ok else '없음(GEMINI_API_KEY)'}"
    if LLM_PROVIDER == "openai":
        ok = bool(os.getenv("OPENAI_API_KEY"))
        return ok, f"provider=openai model={OPENAI_MODEL} key={'OK' if ok else '없음(OPENAI_API_KEY)'}"
    return False, f"알 수 없는 provider: {LLM_PROVIDER}"


if __name__ == "__main__":
    ok, info = is_configured()
    print(f"[LLM 설정] {info}")
    if not ok:
        print("API 키가 없어 호출 테스트를 건너뜁니다. .env 또는 환경변수를 설정하세요.")
        raise SystemExit(0)

    print("\n[테스트 호출]")
    out = call_llm(
        "당신은 친절한 한국어 도우미입니다. 한 문장으로만 답하세요.",
        "국가유산 해설사 챗봇이 곧 완성된다는 소식을 멋지게 축하해줘.",
    )
    print(out)
