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
sys.path.append(str(ROOT))
sys.path.append(str(ROOT / "backend"))

from app.db.session import SessionLocal  # noqa: E402
from app.models.heritage import DocumentChunk, Heritage  # noqa: E402
from app.services.chunking import chunk_text  # noqa: E402
from app.services.embedding import embed_text  # noqa: E402
from scripts.build_heritage_json_v1 import build_facets, fetch_events, match_events  # noqa: E402

LIST_URL = "https://www.khs.go.kr/cha/SearchKindOpenapiList.do"
DETAIL_URL = "https://www.khs.go.kr/cha/SearchKindOpenapiDt.do"
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


def fetch_list_page(client: httpx.Client, page_index: int, page_unit: int, category: str | None = None, region: str | None = None) -> tuple[int, list[dict[str, Any]]]:
    params: dict[str, Any] = {"pageUnit": page_unit, "pageIndex": page_index}
    if category:
        params["ccbaKdcd"] = category
    if region:
        params["ccbaCtcd"] = region
    response = client.get(LIST_URL, params=params, timeout=20)
    response.raise_for_status()
    root = ET.fromstring(response.text)
    total = int(root.findtext("totalCnt") or 0)
    return total, parse_items(response.text)


def iter_list(client: httpx.Client, page_unit: int, category: str | None = None, region: str | None = None):
    page_index = 1
    fetched = 0
    while True:
        total, items = fetch_list_page(client, page_index, page_unit, category=category, region=region)
        if not items:
            break
        for item in items:
            fetched += 1
            yield item
        if fetched >= total:
            break
        page_index += 1


def fetch_list(client: httpx.Client, category: str, region: str) -> list[dict[str, Any]]:
    _, items = fetch_list_page(client, 1, 100, category=category, region=region)
    return items


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


def normalize(item: dict[str, Any], detail: dict[str, Any], events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    ccba_kdcd = str(first(item.get("ccbaKdcd"), detail.get("ccbaKdcd")))
    ccba_asno = str(first(item.get("ccbaAsno"), detail.get("ccbaAsno")))
    ccba_ctcd = str(first(item.get("ccbaCtcd"), detail.get("ccbaCtcd")))
    content = clean_html(first(detail.get("content"), detail.get("ccceName"), detail.get("ccbaContent")))
    source_url = f"{DETAIL_URL}?ccbaKdcd={ccba_kdcd}&ccbaAsno={ccba_asno}&ccbaCtcd={ccba_ctcd}"
    address = first(detail.get("ccbaLcad"), item.get("ccbaLcad"))
    latitude = float(first(detail.get("latitude"), item.get("latitude"))) if first(detail.get("latitude"), item.get("latitude")) else None
    longitude = float(first(detail.get("longitude"), item.get("longitude"))) if first(detail.get("longitude"), item.get("longitude")) else None
    facets = build_facets(content or "", address, latitude, longitude)
    matched_events = match_events(
        {
            "names": {"ko": first(detail.get("ccbaMnm1"), item.get("ccbaMnm1"), item.get("ccbaMnm2"), "이름 미상")},
            "location": {"region": first(detail.get("ccbaCtcdNm"), item.get("ccbaCtcdNm"), REGIONS.get(ccba_ctcd)), "district": detail.get("ccsiName")},
        },
        events or [],
    )
    facets["travel_visit"]["related_events"] = [
        {
            "title": event.get("title"),
            "place": event.get("venue"),
            "date": event.get("date_text"),
            "url": event.get("url"),
            "region": event.get("region"),
            "district": event.get("district"),
        }
        for event in matched_events
    ]
    facets["travel_visit"].pop("events", None)

    return {
        "ccba_kdcd": ccba_kdcd,
        "ccba_asno": ccba_asno,
        "ccba_ctcd": ccba_ctcd,
        "name": first(detail.get("ccbaMnm1"), item.get("ccbaMnm1"), item.get("ccbaMnm2"), "이름 미상"),
        "category": first(detail.get("ccmaName"), item.get("ccmaName"), CATEGORIES.get(ccba_kdcd)),
        "region": first(detail.get("ccbaCtcdNm"), item.get("ccbaCtcdNm"), REGIONS.get(ccba_ctcd)),
        "era": first(detail.get("ccceName"), detail.get("ccbaAge")),
        "address": address,
        "latitude": latitude,
        "longitude": longitude,
        "image_url": first(detail.get("imageUrl"), detail.get("ccimDesc")),
        "content": content,
        "source_url": source_url,
        "facet_json": facets,
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
    parser.add_argument("--all", action="store_true", help="Collect all listed heritages across all categories/regions")
    parser.add_argument("--page-unit", type=int, default=1000, help="List API page size when using --all")
    parser.add_argument("--skip-existing", action="store_true", help="Skip detail fetch when a heritage already exists")
    args = parser.parse_args()

    collected = 0
    with httpx.Client(headers={"User-Agent": "heritage-rag-kakao-mk0"}, follow_redirects=True) as client, SessionLocal() as db:
        events = fetch_events(500)
        if args.all:
            for item in iter_list(client, page_unit=args.page_unit):
                if args.limit and collected >= args.limit:
                    db.commit()
                    print(f"collected={collected}")
                    return
                if args.skip_existing:
                    exists = db.query(Heritage.id).filter(
                        Heritage.ccba_kdcd == str(item.get("ccbaKdcd") or ""),
                        Heritage.ccba_asno == str(item.get("ccbaAsno") or ""),
                        Heritage.ccba_ctcd == str(item.get("ccbaCtcd") or ""),
                    ).first()
                    if exists:
                        continue
                detail = fetch_detail(client, item)
                row = normalize(item, detail, events)
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
                if collected % 50 == 0:
                    db.commit()
                print(json.dumps({"collected": collected, "name": row["name"]}, ensure_ascii=False))
            db.commit()
            print(f"collected={collected}")
            return

        for region in REGIONS:
            for category in CATEGORIES:
                for item in fetch_list(client, category, region):
                    if collected >= args.limit:
                        db.commit()
                        print(f"collected={collected}")
                        return
                    detail = fetch_detail(client, item)
                    row = normalize(item, detail, events)
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
