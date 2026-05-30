from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.repository import HeritageRepository
from app.db.session import get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.orchestrator import ChatOrchestrator

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, db: Session = Depends(get_db)):
    repo = HeritageRepository(db)
    repo.init_schema()
    if not repo.list_entities():
        repo.seed_sample_data()
    return ChatOrchestrator(repo).chat(request)
