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


def select_sentences(sentences: list[str], interests: set[str], age_group: str | None) -> list[str]:
    if not sentences:
        return []

    scored: list[tuple[int, int, str]] = []
    for idx, sentence in enumerate(sentences):
        score = 0
        if "architecture" in interests and any(word in sentence for word in ["형태", "직사각형", "돌", "자연암반", "층", "크기", "높이", "너비"]):
            score += 4
        if "people" in interests and any(word in sentence for word in ["진흥왕", "김정희", "왕", "인물"]):
            score += 4
        if "travel" in interests and any(word in sentence for word in ["위치", "주소", "자리", "보관", "박물관", "비봉", "경복궁"]):
            score += 4
        if "story" in interests and any(word in sentence for word in ["발견", "옮겨", "기념", "방문", "알려졌", "세상"]):
            score += 4
        if "quiz" in interests and any(word in sentence for word in ["크기", "높이", "너비", "12행", "32자", "연대", "국보"]):
            score += 4
        # Keep the opening/source-defining sentences important even when no keyword matches.
        if idx <= 1:
            score += 2
        scored.append((score, -idx, sentence))

    if age_group == "elementary":
        limit = 3
    elif age_group == "middle_high":
        limit = 4
    else:
        limit = 5

    picked = sorted(scored, key=lambda item: (-item[0], -item[1]))[:limit]
    # Return in original order for readability.
    return [sentence for _, _, sentence in sorted(picked, key=lambda item: -item[1])]


def rewrite_for_age(sentences: list[str], age_group: str | None) -> str:
    text = " ".join(sentences)
    if not text:
        return "현재 확보된 설명문이 짧아 추가 설명이 필요합니다."

    if age_group == "elementary":
        text = text.replace("편입한 뒤", "차지한 뒤")
        text = text.replace("기념하기 위하여", "기념하려고")
        text = text.replace("보존하기 위하여", "잘 보관하려고")
        text = text.replace("건립연대", "세운 시기")
        return text
    if age_group == "middle_high":
        return text
    if age_group == "senior":
        return text.replace("현재는", "지금은")
    return text


def build_interest_intro(interests: set[str]) -> str:
    if "architecture" in interests:
        return "형태와 구조를 중심으로 보면,"
    if "people" in interests:
        return "관련 인물을 중심으로 보면,"
    if "travel" in interests:
        return "답사 정보 중심으로 보면,"
    if "quiz" in interests:
        return "기억할 핵심을 중심으로 보면,"
    if "story" in interests:
        return "이야기의 흐름으로 보면,"
    return "검색된 국가유산 자료 기준으로,"


def build_personalized_answer(question: str, contexts: list[dict], audience: AudienceProfile | None = None) -> str:
    if not contexts:
        return "현재 확보된 국가유산 데이터에서는 확인하기 어렵습니다."

    context = contexts[0]
    age_group = audience.age_group if audience else None
    interests = set(audience.interests if audience else [])
    name = context.get("name") or "검색된 국가유산"
    meta = " · ".join(x for x in [context.get("category"), context.get("region"), context.get("era")] if x)
    address = context.get("address")
    source_url = context.get("source_url")

    sentences = split_sentences(context.get("chunk_text") or "")
    selected = select_sentences(sentences, interests, age_group)
    summary = rewrite_for_age(selected, age_group)
    intro = build_interest_intro(interests)

    lines = [f"{intro} 지금 확인된 자료는 ‘{name}’입니다."]
    if meta:
        lines.append(meta)
    if address and "travel" in interests:
        lines.append(f"위치: {address}")
    lines.extend(["", summary])
    if source_url:
        lines.extend(["", f"출처: {source_url}"])
    return "\n".join(lines)
