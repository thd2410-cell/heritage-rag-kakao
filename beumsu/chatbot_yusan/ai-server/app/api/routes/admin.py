from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.repository import HeritageRepository
from app.db.session import get_db

router = APIRouter()


@router.get("/admin/entities")
def entities(db: Session = Depends(get_db)):
    repo = HeritageRepository(db)
    repo.init_schema()
    return [
        {"id": e.id, "official_name_ko": e.official_name_ko, "official_name_en": e.official_name_en, "period": e.period}
        for e in repo.list_entities()
    ]


@router.get("/admin/logs")
def logs(db: Session = Depends(get_db)):
    return db.info.get("conversation_logs", [])
