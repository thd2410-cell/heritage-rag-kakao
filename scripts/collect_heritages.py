"""Collect initial KHS heritage data for Seoul/Gyeongbuk and National Treasure/Treasure/Historic Site.

Run after Postgres is up:
    python scripts/collect_heritages.py --limit 50
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import httpx
from sqlalchemy.dialects.postgresql import insert

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "backend"))

from app.db.session import SessionLocal  # noqa: E402
from app.models.heritage import DocumentChunk, Heritage  # noqa: E402
from app.services.chunking import chunk_text  # noqa: E402
from app.services.embedding import embed_text  # noqa: E402

LIST_URL = "http://www.khs.go.kr/cha/SearchKindOpenapiList.do"
DETAIL_URL = "http://www.khs.go.kr/cha/SearchKindOpenapiDt.do"
CATEGORIES = {"11": "국보", "12": "보물", "13": "사적"}
REGIONS = {"11": "서울", "37": "경북"}


def xml_to_dict(elem: ET.Element) -> dict[str, Any]:
    children = list(elem)
    if not children:
        return (elem.text or "").strip()
    result: dict[str, Any] = {}
    for child in children:
        value = xml_to_dict(child)
        if child.tag in result:
            if not isinstance(result[child.tag], list):
                result[child.tag] = [result[child.tag]]
            result[child.tag].append(value)
        else:
            result[child.tag] = value
    return result


def parse_items(xml_text: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    items = []
    for item in root.iter("item"):
        parsed = xml_to_dict(item)
        if isinstance(parsed, dict):
            items.append(parsed)
    return items


def clean_html(text: str | None) -> str | None:
    if not text:
        return None
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def first(*values: Any) -> Any:
    for v in values:
        if v not in (None, ""):
            return v
    return None


def fetch_list(client: httpx.Client, category: str, region: str) -> list[dict[str, Any]]:
    params = {"ccbaKdcd": category, "ccbaCtcd": region, "pageUnit": 100, "pageIndex": 1}
    response = client.get(LIST_URL, params=params, timeout=20)
    response.raise_for_status()
    return parse_items(response.text)


def fetch_detail(client: httpx.Client, item: dict[str, Any]) -> dict[str, Any]:
    params = {
        "ccbaKdcd": item.get("ccbaKdcd"),
        "ccbaAsno": item.get("ccbaAsno"),
        "ccbaCtcd": item.get("ccbaCtcd"),
    }
    response = client.get(DETAIL_URL, params=params, timeout=20)
    response.raise_for_status()
    items = parse_items(response.text)
    return items[0] if items else {}


def normalize(item: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    ccba_kdcd = str(first(item.get("ccbaKdcd"), detail.get("ccbaKdcd")))
    ccba_asno = str(first(item.get("ccbaAsno"), detail.get("ccbaAsno")))
    ccba_ctcd = str(first(item.get("ccbaCtcd"), detail.get("ccbaCtcd")))
    content = clean_html(first(detail.get("content"), detail.get("ccceName"), detail.get("ccbaContent")))
    source_url = f"{DETAIL_URL}?ccbaKdcd={ccba_kdcd}&ccbaAsno={ccba_asno}&ccbaCtcd={ccba_ctcd}"
    return {
        "ccba_kdcd": ccba_kdcd,
        "ccba_asno": ccba_asno,
        "ccba_ctcd": ccba_ctcd,
        "name": first(detail.get("ccbaMnm1"), item.get("ccbaMnm1"), item.get("ccbaMnm2"), "이름 미상"),
        "category": first(detail.get("ccmaName"), item.get("ccmaName"), CATEGORIES.get(ccba_kdcd)),
        "region": first(detail.get("ccbaCtcdNm"), item.get("ccbaCtcdNm"), REGIONS.get(ccba_ctcd)),
        "era": first(detail.get("ccceName"), detail.get("ccbaAge")),
        "address": first(detail.get("ccbaLcad"), item.get("ccbaLcad")),
        "latitude": float(detail["latitude"]) if detail.get("latitude") else None,
        "longitude": float(detail["longitude"]) if detail.get("longitude") else None,
        "image_url": first(detail.get("imageUrl"), detail.get("ccimDesc")),
        "content": content,
        "source_url": source_url,
        "raw_json": {"list": item, "detail": detail},
    }


def upsert_heritage(db, row: dict[str, Any]) -> int:
    stmt = insert(Heritage).values(**row)
    update_cols = {k: getattr(stmt.excluded, k) for k in row if k not in {"ccba_kdcd", "ccba_asno", "ccba_ctcd"}}
    stmt = stmt.on_conflict_do_update(
        index_elements=["ccba_kdcd", "ccba_asno", "ccba_ctcd"],
        set_=update_cols,
    ).returning(Heritage.id)
    return db.execute(stmt).scalar_one()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--no-embed", action="store_true", help="Store heritages only; skip chunk embedding")
    args = parser.parse_args()

    collected = 0
    with httpx.Client(headers={"User-Agent": "heritage-rag-kakao-mk0"}) as client, SessionLocal() as db:
        for region in REGIONS:
            for category in CATEGORIES:
                for item in fetch_list(client, category, region):
                    if collected >= args.limit:
                        db.commit()
                        print(f"collected={collected}")
                        return
                    detail = fetch_detail(client, item)
                    row = normalize(item, detail)
                    heritage_id = upsert_heritage(db, row)
                    db.query(DocumentChunk).filter(DocumentChunk.heritage_id == heritage_id).delete()
                    for idx, chunk in enumerate(chunk_text(row.get("content") or row["name"])):
                        embedding = None if args.no_embed else embed_text(chunk)
                        db.add(DocumentChunk(
                            heritage_id=heritage_id,
                            chunk_text=chunk,
                            embedding=embedding,
                            metadata_json={"chunk_index": idx, "name": row["name"], "source_url": row.get("source_url")},
                        ))
                    collected += 1
                    print(json.dumps({"collected": collected, "name": row["name"]}, ensure_ascii=False))
                    db.commit()
    print(f"collected={collected}")


if __name__ == "__main__":
    main()
