import re

from app.services.personalization import AudienceProfile
from app.services.text_cleaning import remove_unwanted_cjk

def compact_text(text: str) -> str:
    text = remove_unwanted_cjk(text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def split_sentences(text: str) -> list[str]:
    compacted = compact_text(text)
    if not compacted:
        return []
    parts = re.split(r"(?<=[.!?])\s+|(?<=다\.)\s+|(?<=요\.)\s+", compacted)
    return [part.strip() for part in parts if part.strip()]


def summarize_source_text(text: str, age_group: str | None) -> str:
    sentences = split_sentences(text)
    if not sentences:
        return "현재 확보된 설명문이 짧아 추가 설명이 필요합니다."

    if age_group == "elementary":
        limit = 3
    elif age_group == "middle_high":
        limit = 4
    else:
        limit = 5
    return " ".join(sentences[:limit])


def build_followups(context: dict, audience: AudienceProfile | None) -> list[str]:
    name = context.get("name") or "이 국가유산"
    interests = set(audience.interests if audience else [])

    if "quiz" in interests:
        return [
            f"{name}의 핵심 내용을 퀴즈로 내줘",
            f"{name}에서 꼭 기억해야 할 단어 3개는 뭐야?",
        ]
    if "travel" in interests:
        return [
            f"{name}의 위치와 관람 전에 알면 좋은 점을 알려줘",
            f"{name}와 함께 보면 좋은 국가유산을 추천해줘",
        ]
    if "people" in interests:
        return [
            f"{name}와 관련된 인물을 알려줘",
            f"{name}가 만들어진 시대 배경을 설명해줘",
        ]
    if "architecture" in interests:
        return [
            f"{name}의 형태와 구조를 설명해줘",
            f"{name}에서 눈여겨볼 부분은 어디야?",
        ]
    return [
        f"{name}의 역사적 의미를 더 자세히 알려줘",
        f"{name}를 쉽게 기억하는 방법을 알려줘",
    ]


def build_personalized_answer(question: str, contexts: list[dict], audience: AudienceProfile | None = None) -> str:
    if not contexts:
        return "현재 확보된 국가유산 데이터에서는 확인하기 어렵습니다."

    context = contexts[0]
    age_group = audience.age_group if audience else None
    name = context.get("name") or "검색된 국가유산"
    meta = " · ".join(x for x in [context.get("category"), context.get("region"), context.get("era")] if x)
    address = context.get("address")
    source_url = context.get("source_url")
    summary = summarize_source_text(context.get("chunk_text") or "", age_group)

    prefix_by_age = {
        "elementary": "쉽게 말하면,",
        "middle_high": "핵심부터 보면,",
        "adult": "검색된 국가유산 자료 기준으로,",
        "senior": "차근차근 설명하면,",
    }
    prefix = prefix_by_age.get(age_group or "", "검색된 국가유산 자료 기준으로,")

    lines = [f"{prefix} 지금 확인된 자료는 ‘{name}’입니다."]
    if meta:
        lines.append(meta)
    if address:
        lines.append(f"위치: {address}")
    lines.extend(["", summary])
    if source_url:
        lines.extend(["", f"출처: {source_url}"])

    followups = build_followups(context, audience)
    lines.extend(["", "다음에 물어볼 만한 질문:"])
    lines.extend(f"{idx}. {item}" for idx, item in enumerate(followups, start=1))
    return "\n".join(lines)
