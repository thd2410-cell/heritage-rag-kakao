"""Backfill embeddings for document_chunks.

Usage:
    python scripts/embed_chunks.py --batch-size 32

The script is resumable: it only processes rows where embedding IS NULL.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from time import monotonic

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "backend"))

from app.db.session import SessionLocal  # noqa: E402
from app.services.embedding import get_embedding_model  # noqa: E402


def fetch_batch(db, batch_size: int):
    return db.execute(
        text(
            """
            SELECT id, chunk_text
            FROM document_chunks
            WHERE embedding IS NULL
            ORDER BY id
            LIMIT :batch_size
            """
        ),
        {"batch_size": batch_size},
    ).mappings().all()


def update_embeddings(db, ids: list[int], vectors: list[list[float]]) -> None:
    for chunk_id, vector in zip(ids, vectors, strict=True):
        db.execute(
            text("UPDATE document_chunks SET embedding = CAST(:embedding AS vector) WHERE id = :id"),
            {"id": chunk_id, "embedding": "[" + ",".join(str(float(x)) for x in vector) + "]"},
        )


def counts(db) -> tuple[int, int]:
    total = db.execute(text("SELECT count(*) FROM document_chunks")).scalar_one()
    done = db.execute(text("SELECT count(*) FROM document_chunks WHERE embedding IS NOT NULL")).scalar_one()
    return int(total), int(done)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--max-batches", type=int, default=0, help="0 means no limit")
    args = parser.parse_args()

    model = get_embedding_model()
    started = monotonic()
    processed = 0
    batch_no = 0

    with SessionLocal() as db:
        total, done = counts(db)
        print(f"start total={total} embedded={done} remaining={total - done}", flush=True)
        while True:
            if args.max_batches and batch_no >= args.max_batches:
                break
            rows = fetch_batch(db, args.batch_size)
            if not rows:
                break
            ids = [int(row["id"]) for row in rows]
            texts = [row["chunk_text"] or "" for row in rows]
            vectors = model.encode(texts, normalize_embeddings=True, batch_size=args.batch_size)
            update_embeddings(db, ids, vectors.astype(float).tolist())
            db.commit()
            processed += len(ids)
            batch_no += 1
            total, done = counts(db)
            elapsed = monotonic() - started
            rate = processed / elapsed if elapsed > 0 else 0
            print(
                f"batch={batch_no} processed={processed} embedded={done}/{total} "
                f"remaining={total - done} rate={rate:.2f}/s",
                flush=True,
            )

    with SessionLocal() as db:
        total, done = counts(db)
        print(f"done total={total} embedded={done} remaining={total - done}", flush=True)


if __name__ == "__main__":
    main()
