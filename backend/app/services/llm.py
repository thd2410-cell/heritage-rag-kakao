import httpx
from openai import OpenAI
from app.core.config import get_settings

SYSTEM_PROMPT = """너는 국가유산 전문 AI 해설사다.
반드시 제공된 검색 근거 안에서만 답변한다.
근거가 부족하면 추측하지 말고 '현재 확보된 국가유산 데이터에서는 확인하기 어렵습니다.'라고 말한다.
답변에는 가능한 한 출처/유산명을 포함한다.
일반 상식, 프로그래밍, 날씨, 금융 등 국가유산과 무관한 질문에는 답변하지 않는다.
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
        return "객관식 4지선다 퀴즈 1개를 만들고, 정답과 해설을 포함해줘."
    if mode == "easy":
        return "초등학생도 이해할 수 있게 쉽고 짧게 설명해줘."
    if mode == "deep":
        return "역사적 의미, 시대 배경, 관련 인물을 중심으로 심화 설명해줘."
    if mode == "recommend":
        return "검색 근거의 시대, 지역, 주제를 바탕으로 관련 국가유산을 추천해줘."
    return "핵심 설명을 간결하게 제공해줘."


def build_user_prompt(question: str, contexts: list[dict]) -> str:
    mode = infer_mode(question)
    context_text = "\n\n---\n\n".join(
        f"유산명: {c.get('name')}\n분류: {c.get('category')}\n지역: {c.get('region')}\n시대: {c.get('era')}\n주소: {c.get('address')}\n출처: {c.get('source_url')}\n내용:\n{c.get('chunk_text')}"
        for c in contexts
    )
    return f"질문: {question}\n\n요청 형식: {build_instruction(mode)}\n\n검색 근거:\n{context_text}"


def generate_with_ollama(question: str, contexts: list[dict]) -> str:
    settings = get_settings()
    response = httpx.post(
        f"{settings.ollama_base_url.rstrip('/')}/api/chat",
        json={
            "model": settings.ollama_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(question, contexts)},
            ],
            "stream": False,
            "options": {"temperature": 0.2},
        },
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()
    return data.get("message", {}).get("content") or "현재 확보된 국가유산 데이터에서는 확인하기 어렵습니다."


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
        temperature=0.2,
    )
    return response.choices[0].message.content or "현재 확보된 국가유산 데이터에서는 확인하기 어렵습니다."


def generate_answer(question: str, contexts: list[dict]) -> str:
    settings = get_settings()
    if settings.llm_provider.lower() == "ollama":
        return generate_with_ollama(question, contexts)
    return generate_with_openai(question, contexts)
