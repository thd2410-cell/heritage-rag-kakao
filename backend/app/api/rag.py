from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.heritage import ChatLog
from app.services.domain import OUT_OF_DOMAIN_MESSAGE, is_heritage_domain
from app.services.guardrails import check_guardrail
from app.services.answer_builder import build_personalized_answer
from app.services.conversation import recent_audience, resolve_contextual_question, with_conversation_meta
from app.services.personalization import AudienceProfile
from app.services.retrieval import search_chunks

router = APIRouter(prefix="/api/rag", tags=["rag"])


class AskRequest(BaseModel):
    question: str
    audience: AudienceProfile | None = Field(default=None)
    session_id: str | None = Field(default=None)


@router.post("/ask")
def ask(payload: AskRequest, db: Session = Depends(get_db)):
    blocked = check_guardrail(payload.question)
    if blocked:
        return {"answer": blocked, "sources": []}

    resolution = resolve_contextual_question(db, payload.question, payload.session_id)
    if resolution.needs_clarification:
        return {"answer": resolution.clarification, "sources": [], "needs_clarification": True}

    audience = payload.audience or recent_audience(db, payload.session_id)
    contexts = search_chunks(db, resolution.question, limit=3)
    if not is_heritage_domain(resolution.question) and not contexts:
        return {"answer": OUT_OF_DOMAIN_MESSAGE, "sources": []}
    if not contexts:
        return {"answer": "현재 확보된 국가유산 데이터에서는 확인하기 어렵습니다.", "sources": []}
    answer = build_personalized_answer(resolution.question, contexts, audience)
    if payload.session_id:
        db.add(
            ChatLog(
                user_key=payload.session_id,
                utterance=payload.question,
                answer=answer,
                sources=with_conversation_meta(contexts, audience, resolution.question),
            )
        )
        db.commit()
    return {"answer": answer, "sources": contexts, "resolved_question": resolution.question, "context_mode": resolution.mode}
