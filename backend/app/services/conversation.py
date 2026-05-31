from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.heritage import ChatLog
from app.services.domain import is_heritage_domain
from app.services.personalization import AudienceProfile
from app.services.retrieval import apply_common_aliases, search_chunks

FOLLOWUP_HINTS = ["더 자세", "자세히", "심화", "이어서", "계속", "그거", "그 유산", "방금"]
TOPIC_SHIFT_HINTS = ["알려줘", "설명", "뭐야", "무엇", "어때", "추천"]
RETURN_TOPIC_HINTS = ["아까", "이전", "전에", "방금 전"]
ROOT_TOPIC_HINTS = ["처음", "원래", "처음에", "처음 말한"]
CONTEXTUAL_HINTS = [
    "건축", "구조", "형태", "공간", "역사", "시대", "의미", "특징", "가치", "인물", "왕", "누가",
    "어디", "위치", "주소", "근처", "주변", "행사", "답사", "여행", "가는", "볼만", "화재", "복원",
    "전설", "이야기", "유래", "왜", "어떻게", "언제", "몇", "차이", "비교", "만든", "지은", "보관",
    "공개", "사진", "이미지", "입장", "관람", "동선", "코스", "소요", "시간", "볼거리",
]
REFERENCE_HINTS = FOLLOWUP_HINTS + RETURN_TOPIC_HINTS + ROOT_TOPIC_HINTS + ["이거", "저거", "이 유산", "저 유산"]


@dataclass
class ConversationResolution:
    question: str
    subject: str | None = None
    mode: str = "standalone"
    needs_clarification: bool = False
    clarification: str | None = None


def _extract_source_name(sources: object) -> str | None:
    if isinstance(sources, list) and sources:
        first = sources[0]
        if isinstance(first, dict):
            return first.get("name")
    return None


def recent_subjects(db: Session, session_id: str | None, limit: int = 5) -> list[str]:
    if not session_id:
        return []
    logs = (
        db.query(ChatLog)
        .filter(ChatLog.user_key == session_id)
        .order_by(ChatLog.id.desc())
        .limit(16)
        .all()
    )
    subjects: list[str] = []
    for log in logs:
        name = _extract_source_name(log.sources)
        if name and name not in subjects:
            subjects.append(name)
            if len(subjects) >= limit:
                break
    return subjects


def recent_audience(db: Session, session_id: str | None) -> AudienceProfile | None:
    if not session_id:
        return None
    logs = (
        db.query(ChatLog)
        .filter(ChatLog.user_key == session_id)
        .order_by(ChatLog.id.desc())
        .limit(10)
        .all()
    )
    for log in logs:
        sources = log.sources or []
        if not isinstance(sources, list):
            continue
        for source in sources:
            if not isinstance(source, dict):
                continue
            meta = source.get("__conversation")
            if isinstance(meta, dict) and isinstance(meta.get("audience"), dict):
                try:
                    return AudienceProfile.model_validate(meta["audience"])
                except Exception:
                    continue
    return None


def with_conversation_meta(contexts: list[dict], audience: AudienceProfile | None, resolved_question: str) -> list[dict]:
    if not audience:
        return contexts
    stamped = [dict(context) for context in contexts]
    stamped.append(
        {
            "__conversation": {
                "audience": audience.model_dump(),
                "resolved_question": resolved_question,
            }
        }
    )
    return stamped


def search_explicit_subject(db: Session, question: str) -> dict | None:
    """Return a likely explicitly-mentioned heritage, if the user named one.

    This is intentionally stricter than general retrieval. Short follow-ups like
    "건축적으로 설명해줘" should not jump to an unrelated record just because a
    content word matched.
    """
    contexts = search_chunks(db, question, limit=1)
    if not contexts:
        return None
    top = contexts[0]
    name = top.get("name") or ""
    metadata = top.get("metadata_json") or {}
    score = top.get("score")
    normalized_question = question.replace(" ", "")
    normalized_aliased_question = apply_common_aliases(question).replace(" ", "")
    normalized_name = name.replace(" ", "")

    if normalized_name and normalized_name in normalized_question:
        return top
    if normalized_name and normalized_name in normalized_aliased_question:
        return top
    if metadata.get("fallback") == "fuzzy_name" and float(metadata.get("fuzzy_score") or 0) >= 0.78:
        return top
    if score is not None and float(score) >= 0.78 and any(hint in question for hint in TOPIC_SHIFT_HINTS):
        return top
    return None


def is_contextual_question(question: str) -> bool:
    return (
        is_heritage_domain(question)
        or any(hint in question for hint in FOLLOWUP_HINTS)
        or any(hint in question for hint in CONTEXTUAL_HINTS)
    )


def needs_subject_clarification(question: str) -> bool:
    return any(hint in question for hint in REFERENCE_HINTS + CONTEXTUAL_HINTS)


def choose_subject(question: str, subjects: list[str]) -> tuple[str | None, str]:
    if not subjects:
        return None, "none"
    if any(hint in question for hint in ROOT_TOPIC_HINTS):
        return subjects[-1], "root_topic"
    if len(subjects) > 1 and any(hint in question for hint in RETURN_TOPIC_HINTS):
        return subjects[1], "previous_topic"
    return subjects[0], "current_topic"


def resolve_contextual_question(db: Session, question: str, session_id: str | None) -> ConversationResolution:
    subjects = recent_subjects(db, session_id)
    explicit = search_explicit_subject(db, question)
    if explicit:
        return ConversationResolution(question=question, subject=explicit.get("name"), mode="explicit_subject")

    subject, mode = choose_subject(question, subjects)
    if subject and is_contextual_question(question):
        return ConversationResolution(question=f"{subject}에 대해 {question}", subject=subject, mode=mode)

    if not subject and needs_subject_clarification(question):
        return ConversationResolution(
            question=question,
            mode="clarify_subject",
            needs_clarification=True,
            clarification="어떤 국가유산에 대해 말하는지 알려줘. 예: ‘숭례문 근처에 뭐 있어?’처럼 유산명을 같이 적어주면 이어서 설명할게.",
        )

    return ConversationResolution(question=question, subject=subject, mode="standalone")
