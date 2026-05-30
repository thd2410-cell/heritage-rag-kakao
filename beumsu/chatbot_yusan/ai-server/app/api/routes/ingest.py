from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.repository import HeritageRepository
from app.db.session import get_db
from app.services.ingest.khs_client import KhsOpenApiClient
from app.services.ingest.khs_text_job import DEFAULT_CTCDS, khs_text_jobs
from app.services.ingest.embedding_job import embedding_jobs
from app.services.ingest.loaders import OfficialDataLoader

router = APIRouter()


class OfficialIngestRequest(BaseModel):
    path: str = Field(default="/app/ai-server/data/import")
    chunk_size: int = Field(default=900, ge=200, le=3000)


class KhsImageIngestRequest(BaseModel):
    heritage_entity_id: str
    ccba_kdcd: str
    ccba_asno: str
    ccba_ctcd: str


class KhsBulkIngestRequest(BaseModel):
    ccba_ctcds: list[str] = Field(default_factory=lambda: ["11"])
    ccba_kdcd: str | None = None
    page_unit: int = Field(default=50, ge=1, le=200)
    max_pages: int = Field(default=1, ge=1, le=200)
    limit: int | None = Field(default=50, ge=1, le=20000)
    include_images: bool = True
    chunk_size: int = Field(default=900, ge=200, le=3000)


class KhsTextJobRequest(BaseModel):
    ccba_ctcds: list[str] = Field(default_factory=lambda: DEFAULT_CTCDS)
    page_unit: int = Field(default=100, ge=1, le=200)
    max_pages_per_ctcd: int | None = Field(default=None, ge=1, le=1000)
    retry_count: int = Field(default=3, ge=1, le=10)
    retry_backoff_seconds: float = Field(default=1.5, ge=0.1, le=30.0)
    page_delay_seconds: float = Field(default=0.0, ge=0.0, le=60.0)
    detail_delay_seconds: float = Field(default=0.0, ge=0.0, le=10.0)
    chunk_size: int = Field(default=900, ge=200, le=3000)


class EmbeddingRebuildRequest(BaseModel):
    batch_size: int = Field(default=64, ge=1, le=256)
    max_chunks: int | None = Field(default=None, ge=1, le=200000)


@router.post("/ingest/sample")
def ingest_sample(db: Session = Depends(get_db)):
    repo = HeritageRepository(db)
    repo.init_schema()
    return repo.seed_sample_data()


@router.post("/ingest/official")
def ingest_official(request: OfficialIngestRequest, db: Session = Depends(get_db)):
    repo = HeritageRepository(db)
    repo.init_schema()
    dataset = OfficialDataLoader().load(request.path)
    result = repo.ingest_official_dataset(dataset, chunk_size=request.chunk_size)
    return {"source_path": request.path, **result}


@router.post("/ingest/khs/images")
def ingest_khs_images(request: KhsImageIngestRequest, db: Session = Depends(get_db)):
    repo = HeritageRepository(db)
    repo.init_schema()
    rows = KhsOpenApiClient().search_images(
        ccba_kdcd=request.ccba_kdcd,
        ccba_asno=request.ccba_asno,
        ccba_ctcd=request.ccba_ctcd,
    )
    images = [{**row, "heritage_entity_id": request.heritage_entity_id} for row in rows]
    result = repo.ingest_official_dataset({"images": images})
    return {"heritage_entity_id": request.heritage_entity_id, "fetched": len(rows), **result}


@router.post("/ingest/khs/bulk")
def ingest_khs_bulk(request: KhsBulkIngestRequest, db: Session = Depends(get_db)):
    repo = HeritageRepository(db)
    repo.init_schema()
    dataset = KhsOpenApiClient().build_dataset_from_khs(
        ccba_ctcds=request.ccba_ctcds,
        page_unit=request.page_unit,
        max_pages=request.max_pages,
        limit=request.limit,
        ccba_kdcd=request.ccba_kdcd,
        include_images=request.include_images,
    )
    result = repo.ingest_official_dataset(dataset, chunk_size=request.chunk_size)
    return {
        "requested": request.model_dump(),
        "fetched_entities": len(dataset["entities"]),
        **result,
    }


@router.post("/ingest/khs/text-jobs")
def start_khs_text_job(request: KhsTextJobRequest):
    return khs_text_jobs.start(**request.model_dump())


@router.get("/ingest/khs/text-jobs")
def list_khs_text_jobs():
    return khs_text_jobs.list_jobs()


@router.get("/ingest/khs/text-jobs/{job_id}")
def get_khs_text_job(job_id: str):
    return khs_text_jobs.status(job_id)


@router.get("/ingest/embeddings/status")
def embedding_status(db: Session = Depends(get_db)):
    repo = HeritageRepository(db)
    repo.init_schema()
    return repo.count_embedding_vectors()


@router.post("/ingest/embeddings/rebuild")
def rebuild_embeddings(request: EmbeddingRebuildRequest):
    return embedding_jobs.start(batch_size=request.batch_size, max_chunks=request.max_chunks)


@router.get("/ingest/embeddings/jobs")
def list_embedding_jobs():
    return embedding_jobs.list_jobs()


@router.get("/ingest/embeddings/jobs/{job_id}")
def get_embedding_job(job_id: str):
    return embedding_jobs.status(job_id)
