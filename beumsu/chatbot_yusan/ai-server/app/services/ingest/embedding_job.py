from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock, Thread
from uuid import uuid4

from app.db.repository import HeritageRepository
from app.db.session import SessionLocal
from app.services.retrieval.vector_retriever import build_embedding_provider


class EmbeddingJobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, dict] = {}
        self._lock = Lock()

    def start(self, batch_size: int = 64, max_chunks: int | None = None) -> dict:
        job_id = str(uuid4())
        job = {
            "job_id": job_id,
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
            "batch_size": batch_size,
            "max_chunks": max_chunks,
            "embedded": 0,
            "failed": 0,
            "before": {},
            "after": {},
            "recent_logs": [],
            "error": None,
        }
        with self._lock:
            self._jobs[job_id] = job
        Thread(target=self._run, args=(job_id,), daemon=True).start()
        return self.status(job_id)

    def list_jobs(self) -> list[dict]:
        with self._lock:
            return list(self._jobs.values())

    def status(self, job_id: str) -> dict:
        with self._lock:
            if job_id not in self._jobs:
                return {"job_id": job_id, "status": "not_found"}
            return dict(self._jobs[job_id])

    def _run(self, job_id: str) -> None:
        provider = build_embedding_provider()
        db = SessionLocal()
        repo = HeritageRepository(db)
        try:
            repo.init_schema()
            self._update(job_id, before=repo.count_embedding_vectors())
            total_embedded = 0
            while True:
                job = self.status(job_id)
                max_chunks = job["max_chunks"]
                if max_chunks is not None and total_embedded >= max_chunks:
                    break
                remaining = None if max_chunks is None else max_chunks - total_embedded
                limit = min(job["batch_size"], remaining) if remaining is not None else job["batch_size"]
                rows = repo.chunks_missing_embedding(limit=limit)
                if not rows:
                    break
                texts = [row["content"] for row in rows]
                try:
                    vectors = provider.embed_batch(texts)
                    for row, vector in zip(rows, vectors):
                        repo.update_chunk_embedding_vector(row["id"], vector)
                    db.commit()
                    total_embedded += len(rows)
                    self._log(job_id, f"embedded batch chunks={len(rows)} total={total_embedded}")
                    self._update(job_id, embedded=total_embedded)
                except Exception as exc:
                    db.rollback()
                    self._log(job_id, f"failed batch size={len(rows)} error={exc}")
                    self._update(job_id, failed=job["failed"] + len(rows))
                    raise
            self._update(
                job_id,
                status="completed",
                finished_at=datetime.now(timezone.utc).isoformat(),
                after=repo.count_embedding_vectors(),
            )
        except Exception as exc:
            self._update(
                job_id,
                status="failed",
                finished_at=datetime.now(timezone.utc).isoformat(),
                error=str(exc),
                after=repo.count_embedding_vectors(),
            )
        finally:
            db.close()

    def _log(self, job_id: str, message: str) -> None:
        with self._lock:
            logs = self._jobs[job_id]["recent_logs"]
            logs.append({"at": datetime.now(timezone.utc).isoformat(), "message": message})
            self._jobs[job_id]["recent_logs"] = logs[-50:]

    def _update(self, job_id: str, **fields) -> None:
        with self._lock:
            self._jobs[job_id].update(fields)


embedding_jobs = EmbeddingJobManager()
