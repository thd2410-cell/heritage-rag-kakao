from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.domain import OUT_OF_DOMAIN_MESSAGE, is_heritage_domain
from app.services.answer_builder import build_personalized_answer
from app.services.personalization import AudienceProfile
from app.services.retrieval import search_chunks

router = APIRouter(prefix="/api/rag", tags=["rag"])


class AskRequest(BaseModel):
    question: str
    audience: AudienceProfile | None = Field(default=None)


@router.post("/ask")
def ask(payload: AskRequest, db: Session = Depends(get_db)):
    contexts = search_chunks(db, payload.question, limit=3)
    if not is_heritage_domain(payload.question) and not contexts:
        return {"answer": OUT_OF_DOMAIN_MESSAGE, "sources": []}
    if not contexts:
        return {"answer": "현재 확보된 국가유산 데이터에서는 확인하기 어렵습니다.", "sources": []}
    return {"answer": build_personalized_answer(payload.question, contexts, payload.audience), "sources": contexts}
