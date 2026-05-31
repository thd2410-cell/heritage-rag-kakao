from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.heritage import ChatLog
from app.schemas.kakao import KakaoSkillRequest
from app.services.conversation import resolve_contextual_question
from app.services.domain import OUT_OF_DOMAIN_MESSAGE, is_heritage_domain
from app.services.guardrails import check_guardrail
from app.services.retrieval import search_chunks
from app.services.text_cleaning import remove_unwanted_cjk

router = APIRouter(prefix="/api/kakao", tags=["kakao"])

QUICK_REPLIES = [
    {"label": "쉽게 설명", "action": "message", "messageText": "쉽게 설명해줘"},
    {"label": "심화 설명", "action": "message", "messageText": "심화 설명해줘"},
    {"label": "위치/근처", "action": "message", "messageText": "근처에 뭐 있어?"},
    {"label": "관련 유산", "action": "message", "messageText": "관련 유산 추천해줘"},
]


def kakao_text_response(text: str) -> dict:
    safe_text = remove_unwanted_cjk(text)
    return {
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": safe_text[:1000]}}],
            "quickReplies": QUICK_REPLIES,
        },
    }


def build_fast_answer(contexts: list[dict]) -> str:
    if not contexts:
        return "현재 확보된 국가유산 데이터에서는 확인하기 어렵습니다. 다른 유산명이나 지역으로 질문해 주세요."
    c = contexts[0]
    text = (c.get("chunk_text") or "").strip().replace("\n", " ")
    if len(text) > 520:
        text = text[:520].rstrip() + "..."
    lines = [f"{c.get('name')}"]
    meta = " · ".join(x for x in [c.get("category"), c.get("region"), c.get("era")] if x)
    if meta:
        lines.append(meta)
    if c.get("address"):
        lines.append(f"위치: {c.get('address')}")
    lines.append("")
    lines.append(text or "현재 확보된 설명문이 짧아 추가 설명이 필요합니다.")
    lines.append("")
    lines.append("※ 국가유산청 Open API 기반 요약입니다.")
    return "\n".join(lines)


@router.post("/skill")
def kakao_skill(payload: KakaoSkillRequest, db: Session = Depends(get_db)):
    utterance = payload.utterance.strip()
    blocked = check_guardrail(utterance)
    if blocked:
        db.add(ChatLog(user_key=payload.user_key, utterance=utterance, answer=blocked, sources=[]))
        db.commit()
        return kakao_text_response(blocked)

    resolution = resolve_contextual_question(db, utterance, payload.user_key)
    if resolution.needs_clarification:
        return kakao_text_response(resolution.clarification or "어떤 국가유산에 대한 질문인지 알려주세요.")

    contexts = search_chunks(db, resolution.question, limit=3)
    if not is_heritage_domain(resolution.question) and not contexts:
        answer = OUT_OF_DOMAIN_MESSAGE
        db.add(ChatLog(user_key=payload.user_key, utterance=utterance, answer=answer, sources=[]))
        db.commit()
        return kakao_text_response(answer)

    answer = remove_unwanted_cjk(build_fast_answer(contexts))
    db.add(ChatLog(user_key=payload.user_key, utterance=utterance, answer=answer, sources=contexts))
    db.commit()
    return kakao_text_response(answer)
