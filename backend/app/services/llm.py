import httpx
from openai import OpenAI
from app.core.config import get_settings
from app.services.text_cleaning import has_unwanted_cjk

SYSTEM_PROMPT = """너는 국가유산 전문 AI 해설사다.
반드시 제공된 검색 근거 안에서만 답변한다.
근거가 부족하면 추측하지 말고 '현재 확보된 국가유산 데이터에서는 확인하기 어렵습니다.'라고 말한다.
답변에는 가능한 한 출처/유산명을 포함한다.
일반 상식, 프로그래밍, 날씨, 금융 등 국가유산과 무관한 질문에는 답변하지 않는다.

[언어 규칙]
- 반드시 자연스러운 한국어로만 답변한다.
- 중국어 한자어, 중국어 병음, 일본어 가나, 영어 번역 병기를 절대 섞지 않는다.
- 한자는 원문 고유명사나 국가유산 명칭에 이미 포함된 경우에만 최소한으로 허용한다.
- 쉬운 설명에서도 외국어 병기 없이 한국어 낱말로 풀어쓴다.
"""

LANGUAGE_REPAIR_PROMPT = """앞선 답변에 한국어가 아닌 문자가 섞였다.
아래 규칙을 지켜 답변을 다시 작성해라.
- 반드시 한국어만 사용한다.
- 중국어, 병음, 일본어, 영어 번역 병기를 모두 제거한다.
- 원문 고유명사에 필요한 한자 외에는 한자를 쓰지 않는다.
- 검색 근거 밖의 내용은 추가하지 않는다.
"""

def infer_mode(question: str) -> str:
    if "퀴즈" in question or "문제" in question:
        return "quiz"
    if "쉽" in question or "초등" in question:
        return "easy"
    if "심화" in question or "자세" in question or "깊" in question:
        return "deep"
    if "추천" in question or "볼만" in question:
        return "recommend"
    return "default"


def build_instruction(mode: str) -> str:
    if mode == "quiz":
        return "객관식 4지선다 퀴즈 1개를 만들고, 정답과 해설을 포함해줘. 반드시 한국어만 사용해줘."
    if mode == "easy":
        return "초등학생도 이해할 수 있게 쉽고 짧게 설명해줘. 반드시 한국어만 사용하고 외국어 병기는 넣지 마."
    if mode == "deep":
        return "역사적 의미, 시대 배경, 관련 인물을 중심으로 심화 설명해줘. 반드시 한국어만 사용해줘."
    if mode == "recommend":
        return "검색 근거의 시대, 지역, 주제를 바탕으로 관련 국가유산을 추천해줘. 반드시 한국어만 사용해줘."
    return "핵심 설명을 간결하게 제공해줘. 반드시 한국어만 사용해줘."


def build_user_prompt(question: str, contexts: list[dict]) -> str:
    mode = infer_mode(question)
    context_text = "\n\n---\n\n".join(
        f"유산명: {c.get('name')}\n분류: {c.get('category')}\n지역: {c.get('region')}\n시대: {c.get('era')}\n주소: {c.get('address')}\n출처: {c.get('source_url')}\n내용:\n{c.get('chunk_text')}"
        for c in contexts
    )
    return f"질문: {question}\n\n요청 형식: {build_instruction(mode)}\n\n검색 근거:\n{context_text}"


def call_ollama(messages: list[dict]) -> str:
    settings = get_settings()
    response = httpx.post(
        f"{settings.ollama_base_url.rstrip('/')}/api/chat",
        json={
            "model": settings.ollama_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.1, "repeat_penalty": 1.08},
        },
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()
    return data.get("message", {}).get("content") or "현재 확보된 국가유산 데이터에서는 확인하기 어렵습니다."


def generate_with_ollama(question: str, contexts: list[dict]) -> str:
    user_prompt = build_user_prompt(question, contexts)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    answer = call_ollama(messages)
    if not has_unwanted_cjk(answer):
        return answer

    repaired = call_ollama(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": answer},
            {"role": "user", "content": LANGUAGE_REPAIR_PROMPT},
        ]
    )
    if has_unwanted_cjk(repaired):
        return "답변 생성 중 한국어가 아닌 문자가 섞여 다시 질문해 주세요."
    return repaired


def generate_with_openai(question: str, contexts: list[dict]) -> str:
    settings = get_settings()
    if not settings.openai_api_key:
        names = ", ".join(sorted({c.get("name") for c in contexts if c.get("name")})) or "검색 결과"
        return (
            "[LLM 비활성화: OPENAI_API_KEY가 아직 설정되지 않았습니다]\n"
            f"검색된 근거: {names}\n\n"
            "카카오 응답/검색 파이프라인 검증용 임시 답변입니다. 실제 해설 생성은 API 키 설정 후 동작합니다."
        )

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(question, contexts)},
        ],
        temperature=0.1,
    )
    answer = response.choices[0].message.content or "현재 확보된 국가유산 데이터에서는 확인하기 어렵습니다."
    if has_unwanted_cjk(answer):
        return "답변 생성 중 한국어가 아닌 문자가 섞여 다시 질문해 주세요."
    return answer


def generate_answer(question: str, contexts: list[dict]) -> str:
    settings = get_settings()
    if settings.llm_provider.lower() == "ollama":
        return generate_with_ollama(question, contexts)
    return generate_with_openai(question, contexts)
