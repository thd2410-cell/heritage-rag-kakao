from __future__ import annotations

import math
import threading
import time
from datetime import UTC, datetime
from uuid import uuid4

from app.db.repository import HeritageRepository
from app.db.session import SessionLocal
from app.services.ingest.khs_client import KhsOpenApiClient


DEFAULT_CTCDS = [
    "11",
    "21",
    "22",
    "23",
    "24",
    "25",
    "26",
    "31",
    "32",
    "33",
    "34",
    "35",
    "36",
    "37",
    "38",
    "45",
    "50",
]


class KhsTextIngestJobManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}

    def start(
        self,
        *,
        ccba_ctcds: list[str] | None = None,
        page_unit: int = 100,
        max_pages_per_ctcd: int | None = None,
        retry_count: int = 3,
        retry_backoff_seconds: float = 1.5,
        page_delay_seconds: float = 0.0,
        detail_delay_seconds: float = 0.0,
        chunk_size: int = 900,
    ) -> dict:
        with self._lock:
            running = [job for job in self._jobs.values() if job["status"] == "running"]
            if running:
                return {
                    "accepted": False,
                    "reason": "khs_text_ingest_already_running",
                    "running_job_id": running[0]["job_id"],
                }
            job_id = str(uuid4())
            job = {
                "job_id": job_id,
                "status": "running",
                "started_at": self._now(),
                "finished_at": None,
                "params": {
                    "ccba_ctcds": ccba_ctcds or DEFAULT_CTCDS,
                    "page_unit": page_unit,
                    "max_pages_per_ctcd": max_pages_per_ctcd,
                    "retry_count": retry_count,
                    "retry_backoff_seconds": retry_backoff_seconds,
                    "page_delay_seconds": page_delay_seconds,
                    "detail_delay_seconds": detail_delay_seconds,
                    "chunk_size": chunk_size,
                    "include_images": False,
                },
                "current_ctcd": None,
                "current_page": 0,
                "estimated_total_pages": None,
                "pages_done": 0,
                "entities_seen": 0,
                "ingested": {
                    "entities": 0,
                    "aliases": 0,
                    "documents": 0,
                    "chunks": 0,
                    "relations": 0,
                    "images": 0,
                },
                "failures": [],
                "recent_logs": [],
            }
            self._jobs[job_id] = job

        thread = threading.Thread(target=self._run, args=(job_id,), daemon=True)
        thread.start()
        return {"accepted": True, "job_id": job_id, **self.status(job_id)}

    def status(self, job_id: str) -> dict:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return {"error": "job_not_found", "job_id": job_id}
            return self._copy(job)

    def list_jobs(self) -> list[dict]:
        with self._lock:
            return [self._copy(job) for job in self._jobs.values()]

    def _run(self, job_id: str) -> None:
        client = KhsOpenApiClient(timeout=30.0)
        db = SessionLocal()
        repo = HeritageRepository(db)
        repo.init_schema()
        try:
            params = self.status(job_id)["params"]
            for ctcd in params["ccba_ctcds"]:
                page = 1
                while True:
                    if params["max_pages_per_ctcd"] and page > params["max_pages_per_ctcd"]:
                        break
                    self._update(job_id, current_ctcd=ctcd, current_page=page)
                    try:
                        listed = self._with_retry(
                            job_id,
                            f"list ctcd={ctcd} page={page}",
                            params["retry_count"],
                            params["retry_backoff_seconds"],
                            lambda: client.search_list(
                                ccba_ctcd=ctcd,
                                page_unit=params["page_unit"],
                                page_index=page,
                            ),
                        )
                    except Exception as exc:
                        self._failure(job_id, ctcd, page, "list", exc)
                        break

                    items = listed["items"]
                    total_count = listed.get("total_count", 0)
                    self._estimate_pages(job_id, total_count, params["page_unit"])
                    if not items:
                        self._log(job_id, f"ctcd={ctcd} page={page} empty; stopping ctcd")
                        break

                    try:
                        dataset = self._with_retry(
                            job_id,
                            f"detail+build ctcd={ctcd} page={page}",
                            params["retry_count"],
                            params["retry_backoff_seconds"],
                            lambda: client.build_dataset_from_list_items(
                                items,
                                default_ctcd=ctcd,
                                include_images=False,
                                detail_delay_seconds=params["detail_delay_seconds"],
                            ),
                        )
                        result = repo.ingest_official_dataset(
                            dataset,
                            chunk_size=params["chunk_size"],
                        )
                        self._ingested(job_id, len(items), result)
                        self._log(
                            job_id,
                            f"ctcd={ctcd} page={page} ingested entities={result['entities']} chunks={result['chunks']}",
                        )
                    except Exception as exc:
                        self._failure(job_id, ctcd, page, "detail_or_ingest", exc)

                    if total_count and page * params["page_unit"] >= total_count:
                        break
                    if params["page_delay_seconds"] > 0:
                        time.sleep(params["page_delay_seconds"])
                    page += 1

            self._finish(job_id, "completed")
        except Exception as exc:
            self._failure(job_id, None, None, "fatal", exc)
            self._finish(job_id, "failed")
        finally:
            db.close()

    def _with_retry(self, job_id: str, label: str, retry_count: int, backoff: float, fn):
        last_error = None
        for attempt in range(1, retry_count + 1):
            try:
                if attempt > 1:
                    self._log(job_id, f"retry {attempt}/{retry_count}: {label}")
                return fn()
            except Exception as exc:
                last_error = exc
                self._log(job_id, f"failed attempt {attempt}/{retry_count}: {label}: {exc}")
                time.sleep(backoff * attempt)
        raise last_error

    def _update(self, job_id: str, **fields) -> None:
        with self._lock:
            self._jobs[job_id].update(fields)

    def _estimate_pages(self, job_id: str, total_count: int, page_unit: int) -> None:
        if not total_count:
            return
        with self._lock:
            job = self._jobs[job_id]
            estimated = math.ceil(total_count / page_unit)
            current = job.get("estimated_total_pages") or 0
            job["estimated_total_pages"] = current + max(0, estimated - current)

    def _ingested(self, job_id: str, entities_seen: int, result: dict[str, int]) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job["pages_done"] += 1
            job["entities_seen"] += entities_seen
            for key, value in result.items():
                job["ingested"][key] = job["ingested"].get(key, 0) + value

    def _failure(self, job_id: str, ctcd, page, stage: str, exc: Exception) -> None:
        failure = {
            "at": self._now(),
            "ctcd": ctcd,
            "page": page,
            "stage": stage,
            "error": str(exc),
        }
        with self._lock:
            self._jobs[job_id]["failures"].append(failure)
        self._log(job_id, f"failure ctcd={ctcd} page={page} stage={stage}: {exc}")

    def _finish(self, job_id: str, status: str) -> None:
        with self._lock:
            self._jobs[job_id]["status"] = status
            self._jobs[job_id]["finished_at"] = self._now()

    def _log(self, job_id: str, message: str) -> None:
        with self._lock:
            logs = self._jobs[job_id]["recent_logs"]
            logs.append({"at": self._now(), "message": message})
            del logs[:-100]

    def _copy(self, job: dict) -> dict:
        return {
            **job,
            "params": dict(job["params"]),
            "ingested": dict(job["ingested"]),
            "failures": list(job["failures"]),
            "recent_logs": list(job["recent_logs"]),
        }

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()


khs_text_jobs = KhsTextIngestJobManager()
