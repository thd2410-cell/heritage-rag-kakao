from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.heritage import ChatLog
from app.schemas.kakao import KakaoSkillRequest
from app.services.domain import OUT_OF_DOMAIN_MESSAGE, is_heritage_domain
from app.services.llm import generate_answer
from app.services.retrieval import search_chunks

router = APIRouter(prefix="/api/kakao", tags=["kakao"])

QUICK_REPLIES = [
    {"label": "쉽게 설명", "action": "message", "messageText": "쉽게 설명해줘"},
    {"label": "심화 설명", "action": "message", "messageText": "심화 설명해줘"},
    {"label": "퀴즈", "action": "message", "messageText": "퀴즈 내줘"},
    {"label": "관련 유산", "action": "message", "messageText": "관련 유산 추천해줘"},
]


def kakao_text_response(text: str) -> dict:
    return {
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": text[:1000]}}],
            "quickReplies": QUICK_REPLIES,
        },
    }


@router.post("/skill")
def kakao_skill(payload: KakaoSkillRequest, db: Session = Depends(get_db)):
    utterance = payload.utterance.strip()
    if not is_heritage_domain(utterance):
        answer = OUT_OF_DOMAIN_MESSAGE
        db.add(ChatLog(user_key=payload.user_key, utterance=utterance, answer=answer, sources=[]))
        db.commit()
        return kakao_text_response(answer)

    contexts = search_chunks(db, utterance, limit=3)
    if not contexts:
        answer = "현재 확보된 국가유산 데이터에서는 확인하기 어렵습니다. 다른 유산명이나 지역으로 질문해 주세요."
    else:
        answer = generate_answer(utterance, contexts)
        sources = sorted({c.get("name") for c in contexts if c.get("name")})
        if sources and "출처" not in answer:
            answer += "\n\n근거: " + ", ".join(sources)

    db.add(ChatLog(user_key=payload.user_key, utterance=utterance, answer=answer, sources=contexts))
    db.commit()
    return kakao_text_response(answer)
