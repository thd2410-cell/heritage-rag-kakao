from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.heritage import ChatLog
from app.services.domain import OUT_OF_DOMAIN_MESSAGE, is_heritage_domain
from app.services.guardrails import check_guardrail
from app.services.answer_builder import build_personalized_answer
from app.services.personalization import AudienceProfile
from app.services.retrieval import search_chunks

router = APIRouter(prefix="/api/rag", tags=["rag"])


class AskRequest(BaseModel):
    question: str
    audience: AudienceProfile | None = Field(default=None)
    session_id: str | None = Field(default=None)


FOLLOWUP_HINTS = ["더 자세", "자세히", "심화", "이어서", "계속", "그거", "그 유산", "방금"]


def recent_subject(db: Session, session_id: str | None) -> str | None:
    if not session_id:
        return None
    logs = (
        db.query(ChatLog)
        .filter(ChatLog.user_key == session_id)
        .order_by(ChatLog.id.desc())
        .limit(5)
        .all()
    )
    for log in logs:
        sources = log.sources or []
        if isinstance(sources, list) and sources:
            name = sources[0].get("name") if isinstance(sources[0], dict) else None
            if name:
                return name
    return None


def resolve_followup_question(question: str, subject: str | None) -> str:
    if subject and any(hint in question for hint in FOLLOWUP_HINTS):
        return f"{subject}에 대해 {question}"
    return question


@router.post("/ask")
def ask(payload: AskRequest, db: Session = Depends(get_db)):
    blocked = check_guardrail(payload.question)
    if blocked:
        return {"answer": blocked, "sources": []}

    question = resolve_followup_question(payload.question, recent_subject(db, payload.session_id))
    contexts = search_chunks(db, question, limit=3)
    if not is_heritage_domain(question) and not contexts:
        return {"answer": OUT_OF_DOMAIN_MESSAGE, "sources": []}
    if not contexts:
        return {"answer": "현재 확보된 국가유산 데이터에서는 확인하기 어렵습니다.", "sources": []}
    answer = build_personalized_answer(question, contexts, payload.audience)
    if payload.session_id:
        db.add(ChatLog(user_key=payload.session_id, utterance=payload.question, answer=answer, sources=contexts))
        db.commit()
    return {"answer": answer, "sources": contexts}
