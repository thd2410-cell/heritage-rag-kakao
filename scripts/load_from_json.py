"""Load BK's collected heritages.json into the backend Postgres (pgvector + bge-m3).

검증·운영 공용. DATABASE_URL이 가리키는 DB에 적재 (로컬 docker / 운영 맥미니).
collect_heritages.py(API→DB)와 공존: 이 스크립트는 BK가 모은 json→DB (재수집 X).

전제: docker DB 가동 + 백엔드 deps(sqlalchemy/psycopg/pgvector/pydantic-settings) +
      sentence-transformers + bge-m3.

실행:
  python scripts/load_from_json.py --limit 50      # 테스트 서브셋
  python scripts/load_from_json.py                 # 전체
  python scripts/load_from_json.py --no-embed      # 메타만(임베딩 스킵)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from sqlalchemy.dialects.postgresql import insert

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "backend"))

from app.db.session import SessionLocal  # noqa: E402
from app.models.heritage import DocumentChunk, Heritage  # noqa: E402
from app.services.chunking import chunk_text  # noqa: E402
from app.services.embedding import embed_text  # noqa: E402
from app.services.text_cleaning import remove_unwanted_cjk  # noqa: E402

DEFAULT_JSON = ROOT / "data_eng" / "data" / "heritages.json"
MIN_CONTENT = 50  # 정제 ⑥ 잠정 임계값: 본문 < 50자는 메타만, 임베딩 스킵


def recover_codes(rec: dict) -> tuple[str | None, str | None, str | None]:
    """ccba_ctcd가 json 필드에 없음 → source_url 쿼리스트링에서 복구."""
    q = parse_qs(urlparse(rec.get("source_url", "")).query)
    kdcd = (q.get("ccbaKdcd") or [None])[0]
    asno = (q.get("ccbaAsno") or [None])[0]
    ctcd = (q.get("ccbaCtcd") or [None])[0]
    return kdcd, asno, ctcd


def clean_html(text: str | None) -> str | None:
    """정제 ③: HTML 태그 제거 (collect_heritages.py와 동일 방식, 드리프트 방지)."""
    if not text:
        return None
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def to_row(rec: dict) -> dict | None:
    """heritages.json 한 레코드 → 백엔드 heritages 컬럼 dict. (ctcd 복구 실패 시 None)"""
    kdcd, asno, ctcd = recover_codes(rec)
    if not (kdcd and asno and ctcd):
        return None  # 코드 복구 불가 → 유니크키 못 만듦 → 스킵

    content = clean_html(rec.get("description"))      # ③ HTML 제거
    content = remove_unwanted_cjk(content or "")      # ④ 한자 제거(A안, 백엔드 방식)
    content = content or None

    return {
        "ccba_kdcd": kdcd,
        "ccba_asno": asno,
        "ccba_ctcd": ctcd,
        "name": rec.get("name") or "이름 미상",
        "category": rec.get("category"),
        "region": rec.get("region"),
        "era": rec.get("era"),
        "address": rec.get("location"),
        "latitude": None,
        "longitude": None,
        "image_url": rec.get("image_url") or None,
        "content": content,
        "source_url": rec.get("source_url"),
        # extra 필드는 raw_json 보존 (결정3). name_hanja는 현재 json에 없음(fetcher 미추출).
        "raw_json": {
            "name_hanja": rec.get("name_hanja"),
            "narration_url": rec.get("narration_url"),
            "designation_date": rec.get("designation_date"),
            "parent_id": rec.get("parent_id"),
            "fetched_at": rec.get("fetched_at"),
            "source_api": rec.get("source_api"),
            "original_id": rec.get("id"),
        },
    }


def upsert_heritage(db, row: dict) -> int:
    """on_conflict(ccba_kdcd,asno,ctcd) upsert → heritage id (collect_heritages 패턴)."""
    stmt = insert(Heritage).values(**row)
    update_cols = {
        k: getattr(stmt.excluded, k)
        for k in row
        if k not in {"ccba_kdcd", "ccba_asno", "ccba_ctcd"}
    }
    stmt = stmt.on_conflict_do_update(
        index_elements=["ccba_kdcd", "ccba_asno", "ccba_ctcd"],
        set_=update_cols,
    ).returning(Heritage.id)
    return db.execute(stmt).scalar_one()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-path", default=str(DEFAULT_JSON))
    parser.add_argument("--limit", type=int, default=None, help="N개만 (테스트)")
    parser.add_argument("--no-embed", action="store_true", help="메타만, 임베딩 스킵")
    args = parser.parse_args()

    with open(args.json_path, "r", encoding="utf-8") as f:
        records = json.load(f)
    if args.limit:
        records = records[: args.limit]
    print(f"로드 대상: {len(records)}개 ({args.json_path})")

    loaded = skipped_code = embedded = skipped_short = 0
    with SessionLocal() as db:
        for i, rec in enumerate(records, 1):
            row = to_row(rec)
            if row is None:
                skipped_code += 1
                continue

            heritage_id = upsert_heritage(db, row)
            db.query(DocumentChunk).filter(DocumentChunk.heritage_id == heritage_id).delete()

            content = row.get("content") or ""
            if not args.no_embed and len(content) >= MIN_CONTENT:  # ⑥ 결측치
                for idx, chunk in enumerate(chunk_text(content)):
                    db.add(DocumentChunk(
                        heritage_id=heritage_id,
                        chunk_text=chunk,
                        embedding=embed_text(chunk),
                        metadata_json={
                            "chunk_index": idx,
                            "name": row["name"],
                            "source_url": row.get("source_url"),
                        },
                    ))
                    embedded += 1
            elif len(content) < MIN_CONTENT:
                skipped_short += 1  # 메타는 적재됨, 임베딩만 스킵

            loaded += 1
            if i % 200 == 0:
                db.commit()
                print(f"  [{i}/{len(records)}] 적재 {loaded} / 청크 {embedded} / 짧음 {skipped_short} / 코드불가 {skipped_code}")
        db.commit()

    print(f"\n완료: 적재 {loaded} / 임베딩 청크 {embedded} / 50자미만(메타만) {skipped_short} / ctcd복구실패 {skipped_code}")


if __name__ == "__main__":
    main()
