import re

from app.services.personalization import AudienceProfile
from app.services.text_cleaning import remove_unwanted_cjk

KEYWORDS = {
    "architecture": ["형태", "직사각형", "돌", "자연암반", "층", "크기", "높이", "너비", "행", "자", "새겨"],
    "people": ["진흥왕", "김정희", "왕", "재위", "인물"],
    "travel": ["위치", "주소", "자리", "보관", "박물관", "비봉", "경복궁", "옮겨"],
    "story": ["발견", "옮겨", "기념", "방문", "알려졌", "세상", "원래", "현재"],
    "quiz": ["크기", "높이", "너비", "12행", "32자", "연대", "국보", "재위"],
}


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


def sentences_matching(sentences: list[str], interest: str, limit: int = 2) -> list[str]:
    words = KEYWORDS.get(interest, [])
    matched = [sentence for sentence in sentences if any(word in sentence for word in words)]
    if not matched:
        matched = sentences[:limit]
    return matched[:limit]


def first_sentence(sentences: list[str]) -> str:
    return sentences[0] if sentences else "현재 확보된 설명문이 짧아 추가 설명이 필요합니다."


def rewrite_for_age(text: str, age_group: str | None) -> str:
    if age_group == "elementary":
        text = text.replace("편입한 뒤", "차지한 뒤")
        text = text.replace("기념하기 위하여", "기념하려고")
        text = text.replace("보존하기 위하여", "잘 보관하려고")
        text = text.replace("건립연대", "세운 시기")
        text = text.replace("영토확장", "땅을 넓힌 일")
    elif age_group == "senior":
        text = text.replace("현재는", "지금은")
    return text


def bullet_lines(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items if item]


def facet_evidence(facet_json: dict | None, key: str) -> list[str]:
    if not facet_json:
        return []
    facet = facet_json.get(key) or {}
    return [compact_text(item) for item in facet.get("evidence") or [] if compact_text(item)]


def build_architecture_answer(name: str, sentences: list[str], age_group: str | None, facet_json: dict | None = None) -> list[str]:
    details = facet_evidence(facet_json, "architecture_space") or sentences_matching(sentences, "architecture", limit=3)
    return [
        "형태와 구조 중심으로 정리하면:",
        *bullet_lines(rewrite_for_age(item, age_group) for item in details),
    ]


def build_people_answer(name: str, sentences: list[str], age_group: str | None, facet_json: dict | None = None) -> list[str]:
    details = facet_evidence(facet_json, "people") or sentences_matching(sentences, "people", limit=3)
    return [
        "관련 인물 중심으로 정리하면:",
        *bullet_lines(rewrite_for_age(item, age_group) for item in details),
    ]


def build_travel_answer(name: str, address: str | None, sentences: list[str], age_group: str | None, facet_json: dict | None = None) -> list[str]:
    travel = (facet_json or {}).get("travel_visit") or {}
    details = travel.get("evidence") or sentences_matching(sentences, "travel", limit=3)
    lines = ["답사/방문 정보 중심으로 정리하면:"]
    address = travel.get("address") or address
    latitude = travel.get("latitude")
    longitude = travel.get("longitude")
    if address:
        lines.append(f"- 위치: {address}")
    if latitude is not None and longitude is not None:
        lines.append(f"- 좌표: {latitude}, {longitude}")
    lines.extend(bullet_lines(rewrite_for_age(item, age_group) for item in details))
    nearby = travel.get("nearby_heritages") or []
    if nearby:
        lines.extend(["", "근처 국가유산 후보:"])
        for item in nearby[:5]:
            distance = item.get("distance_km")
            distance_text = f" · 약 {distance}km" if distance is not None else ""
            category = f" · {item.get('category')}" if item.get("category") else ""
            lines.append(f"- {item.get('name')}{distance_text}{category}")
    events = travel.get("related_events") or travel.get("events") or []
    if events:
        lines.extend(["", "관련 행사:"])
        for event in events[:3]:
            place = f" · {event.get('place') or event.get('venue')}" if event.get("place") or event.get("venue") else ""
            date = f" · {event.get('date') or event.get('date_text')}" if event.get("date") or event.get("date_text") else ""
            lines.append(f"- {event.get('title')}{place}{date}")
            if event.get("url"):
                lines.append(f"  {event.get('url')}")
    return lines


def build_story_answer(name: str, sentences: list[str], age_group: str | None, facet_json: dict | None = None) -> list[str]:
    details = facet_evidence(facet_json, "story_legend") or sentences_matching(sentences, "story", limit=4)
    return [
        "이야기 흐름으로 정리하면:",
        *[f"{idx}. {rewrite_for_age(item, age_group)}" for idx, item in enumerate(details, start=1)],
    ]


def build_quiz_answer(name: str, sentences: list[str], age_group: str | None) -> list[str]:
    details = sentences_matching(sentences, "quiz", limit=3)
    return [
        "퀴즈로 기억하기 좋게 정리하면:",
        *bullet_lines(rewrite_for_age(item, age_group) for item in details),
        "",
        "확인 문제:",
        f"1. ‘{name}’은 어떤 시대/인물과 관련이 있을까요?",
        "2. 자료에 나온 크기나 위치 정보 중 하나를 말해볼까요?",
    ]


def build_default_answer(sentences: list[str], age_group: str | None) -> list[str]:
    summary = " ".join(sentences[:4]) if sentences else "현재 확보된 설명문이 짧아 추가 설명이 필요합니다."
    return [rewrite_for_age(summary, age_group)]


def wants_more_detail(question: str) -> bool:
    compact_question = (question or "").replace(" ", "")
    detail_hints = [
        "더 자세", "더자세", "자세히", "자세하게", "상세", "상세히", "상세하게", "심화",
        "깊게", "구체", "풀어서", "더 풀", "더풀", "길게", "더 길", "더길", "예시", "예를",
    ]
    return any(hint in question or hint.replace(" ", "") in compact_question for hint in detail_hints)


def wants_importance(question: str) -> bool:
    compact_question = (question or "").replace(" ", "")
    hints = ["왜 중요", "왜중요", "중요한", "의미", "가치", "왜 유명", "왜유명", "뭐가 특별", "뭐가특별"]
    return any(hint in question or hint.replace(" ", "") in compact_question for hint in hints)


def wants_easy_explanation(question: str) -> bool:
    compact_question = (question or "").replace(" ", "")
    hints = ["쉽게", "쉬운", "초등", "어린", "다시 설명", "다시설명", "풀어서", "이해하기"]
    return any(hint in question or hint.replace(" ", "") in compact_question for hint in hints)


def build_deep_answer(name: str, sentences: list[str], age_group: str | None, facet_json: dict | None = None) -> list[str]:
    architecture = facet_evidence(facet_json, "architecture_space")[:3]
    story = facet_evidence(facet_json, "story_legend")[:3]
    people = facet_evidence(facet_json, "people")[:3]
    lines = ["조금 더 자세히 나누어 보면:"]
    if story:
        lines.extend(["", "이야기/역사 흐름:", *bullet_lines(rewrite_for_age(item, age_group) for item in story)])
    if architecture:
        lines.extend(["", "건축/형태 포인트:", *bullet_lines(rewrite_for_age(item, age_group) for item in architecture)])
    if people:
        lines.extend(["", "관련 인물/시대:", *bullet_lines(rewrite_for_age(item, age_group) for item in people)])
    if len(lines) == 1:
        lines.extend(bullet_lines(rewrite_for_age(item, age_group) for item in sentences[:7]))
    return lines


def build_importance_answer(name: str, sentences: list[str], age_group: str | None, facet_json: dict | None = None) -> list[str]:
    story = facet_evidence(facet_json, "story_legend")[:2]
    architecture = facet_evidence(facet_json, "architecture_space")[:2]
    people = facet_evidence(facet_json, "people")[:2]
    evidence = story + architecture + people
    if not evidence:
        evidence = sentences[:5]
    lines = ["왜 중요하게 보는지 정리하면:"]
    if evidence:
        lines.extend(bullet_lines(rewrite_for_age(item, age_group) for item in evidence[:5]))
    lines.append("")
    lines.append(
        f"정리하면, ‘{name}’은 단순히 오래된 물건이나 장소라기보다 "
        "그 시대의 생활 방식, 기술, 사건, 기억을 지금까지 이어 보여주는 자료라서 중요합니다."
    )
    return lines


def build_easy_answer(name: str, sentences: list[str], facet_json: dict | None = None) -> list[str]:
    story = facet_evidence(facet_json, "story_legend")[:1]
    architecture = facet_evidence(facet_json, "architecture_space")[:1]
    details = story + architecture
    if not details:
        details = sentences[:3]
    simple_details = [rewrite_for_age(item, "elementary") for item in details]
    return [
        "쉽게 말하면:",
        f"- ‘{name}’은 옛사람들이 남긴 중요한 흔적이에요.",
        *bullet_lines(simple_details[:3]),
        f"- 그래서 ‘{name}’을 보면 그 시대 사람들이 무엇을 중요하게 생각했는지 알 수 있어요.",
    ]


def choose_primary_interest(interests: set[str]) -> str | None:
    for interest in ["architecture", "people", "travel", "quiz", "story"]:
        if interest in interests:
            return interest
    return None


def build_personalized_answer(question: str, contexts: list[dict], audience: AudienceProfile | None = None) -> str:
    if not contexts:
        return "현재 확보된 국가유산 데이터에서는 확인하기 어렵습니다."

    context = contexts[0]
    age_group = audience.age_group if audience else None
    interests = set(audience.interests if audience else [])
    primary_interest = choose_primary_interest(interests)

    name = context.get("name") or "검색된 국가유산"
    meta = " · ".join(x for x in [context.get("category"), context.get("region"), context.get("era")] if x)
    address = context.get("address")
    source_url = context.get("source_url")
    facet_json = context.get("facet_json") or {}
    sentences = split_sentences(context.get("chunk_text") or "")

    lines = [f"지금 확인된 자료는 ‘{name}’입니다."]
    if meta:
        lines.append(meta)
    lines.append("")

    if wants_easy_explanation(question):
        lines.extend(build_easy_answer(name, sentences, facet_json))
    elif wants_importance(question):
        lines.extend(build_importance_answer(name, sentences, age_group, facet_json))
    elif wants_more_detail(question):
        lines.extend(build_deep_answer(name, sentences, age_group, facet_json))
    elif primary_interest == "architecture":
        lines.extend(build_architecture_answer(name, sentences, age_group, facet_json))
    elif primary_interest == "people":
        lines.extend(build_people_answer(name, sentences, age_group, facet_json))
    elif primary_interest == "travel":
        lines.extend(build_travel_answer(name, address, sentences, age_group, facet_json))
    elif primary_interest == "quiz":
        lines.extend(build_quiz_answer(name, sentences, age_group))
    elif primary_interest == "story":
        lines.extend(build_story_answer(name, sentences, age_group, facet_json))
    else:
        lines.extend(build_default_answer(sentences, age_group))

    if source_url:
        lines.extend(["", f"출처: {source_url}"])
    return "\n".join(lines)
