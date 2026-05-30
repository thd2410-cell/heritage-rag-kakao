import os

import pytest

os.environ["LLM_PROVIDER"] = "dummy"
os.environ["OPENAI_API_KEY"] = ""

from app.db.repository import HeritageRepository
from app.db.session import SessionLocal


@pytest.fixture()
def repo():
    HeritageRepository.init_schema()
    db = SessionLocal()
    repository = HeritageRepository(db)
    repository.seed_sample_data()
    try:
        yield repository
    finally:
        db.close()
