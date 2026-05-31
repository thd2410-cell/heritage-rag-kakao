"""Build normalized Heritage Chat JSON v1 from KHS OpenAPI list/detail endpoints.

This v1 intentionally uses only:
- SearchKindOpenapiList.do
- SearchKindOpenapiDt.do

Nearby places, events, and GIS enrichment are reserved for later versions.

Examples:
    python scripts/build_heritage_json_v1.py --limit 10 --output data/heritage_v1_sample.json
    python scripts/build_heritage_json_v1.py --regions 11 --categories 11 12 --limit 50
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

LIST_URL = "https://www.khs.go.kr/cha/SearchKindOpenapiList.do"
DETAIL_URL = "https://www.khs.go.kr/cha/SearchKindOpenapiDt.do"
GIS_LOCATION_URL = "https://www.gis-heritage.go.kr/openapi/xmlService/spca.do"
EVENT_URL = "https://www.khs.go.kr/cha/openapi/selectEventListOpenapi.do"

DEFAULT_CATEGORIES = ["11", "12", "13"]  # 국보, 보물, 사적
DEFAULT_REGIONS = ["11", "37"]  # 서울, 경북
CATEGORY_LABELS = {"11": "국보", "12": "보물", "13": "사적"}
REGION_LABELS = {"11": "서울", "37": "경북"}

ARCHITECTURE_KEYWORDS = ["형태", "구조", "건물", "석탑", "목조", "지붕", "기둥", "층", "돌", "크기", "높이", "너비", "양식", "건축"]
STORY_KEYWORDS = ["전설", "이야기", "유래", "기념", "발견", "옮겨", "화재", "복원", "세상", "기록", "사건"]
PEOPLE_KEYWORDS = ["왕", "태조", "세종", "성종", "진흥왕", "김정희", "양녕대군", "인물", "재위", "창건", "건립"]
TRAVEL_KEYWORDS = ["주소", "위치", "소재", "보관", "공개", "일반에 공개", "관리소", "박물관", "자리", "탐방"]


def xml_to_dict(elem: ET.Element) -> Any:
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
    items: list[dict[str, Any]] = []
    for item in root.iter("item"):
        parsed = xml_to_dict(item)
        if isinstance(parsed, dict):
            items.append(parsed)
    return items


def clean_html(text: str | None) -> str:
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\r", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def compact(text: str | None) -> str:
    return re.sub(r"\s+", " ", clean_html(text)).strip()


def first(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def to_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def split_sentences(text: str) -> list[str]:
    text = compact(text)
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+|(?<=다\.)\s+|(?<=요\.)\s+", text)
    return [part.strip() for part in parts if part.strip()]


def pick_sentences(sentences: list[str], keywords: list[str], limit: int = 4) -> list[str]:
    picked = [sentence for sentence in sentences if any(keyword in sentence for keyword in keywords)]
    return picked[:limit]


def build_facets(content: str, address: str | None, latitude: float | None, longitude: float | None) -> dict[str, Any]:
    sentences = split_sentences(content)
    return {
        "architecture_space": {
            "label": "건축/공간",
            "evidence": pick_sentences(sentences, ARCHITECTURE_KEYWORDS),
            "status": "auto_extracted",
        },
        "story_legend": {
            "label": "이야기/전설",
            "evidence": pick_sentences(sentences, STORY_KEYWORDS),
            "status": "auto_extracted",
            "note": "전설 전용 데이터가 아니라 상세 설명문에서 이야기성 문장을 자동 추출한 값입니다.",
        },
        "people": {
            "label": "인물",
            "evidence": pick_sentences(sentences, PEOPLE_KEYWORDS),
            "status": "auto_extracted",
        },
        "travel_visit": {
            "label": "답사/여행",
            "address": address,
            "latitude": latitude,
            "longitude": longitude,
            "spatial_api": {
                "url": GIS_LOCATION_URL,
                "status": "available_for_v1",
                "note": "국가유산 공간정보 API는 지정구역/보호구역 등 공간 레이어 보강용입니다. 1차 JSON에는 목록/상세 좌표를 기본 위치로 넣고, 공간 API 출처를 함께 기록합니다.",
            },
            "evidence": pick_sentences(sentences, TRAVEL_KEYWORDS),
            "nearby_heritages": [],
            "events": [],
            "status": "enriched_v1",
            "note": "근처 맛집/교통은 제외합니다. 근처 국가유산과 국가유산 행사만 공공 API 기반으로 보강합니다.",
        },
    }


def normalize_record(list_item: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    ccba_kdcd = str(first(list_item.get("ccbaKdcd"), detail.get("ccbaKdcd"), ""))
    ccba_asno = str(first(list_item.get("ccbaAsno"), detail.get("ccbaAsno"), ""))
    ccba_ctcd = str(first(list_item.get("ccbaCtcd"), detail.get("ccbaCtcd"), ""))
    content = clean_html(first(detail.get("content"), detail.get("ccceName"), detail.get("ccbaContent")))
    address = compact(first(detail.get("ccbaLcad"), list_item.get("ccbaLcad"))) or None
    source_url = f"{DETAIL_URL}?ccbaKdcd={ccba_kdcd}&ccbaAsno={ccba_asno}&ccbaCtcd={ccba_ctcd}"
    record_id = f"{ccba_kdcd}-{ccba_asno}-{ccba_ctcd}"

    latitude = to_float(first(detail.get("latitude"), list_item.get("latitude")))
    longitude = to_float(first(detail.get("longitude"), list_item.get("longitude")))

    return {
        "schema_version": "heritage-chat.normalized.v1",
        "id": record_id,
        "codes": {
            "ccba_kdcd": ccba_kdcd,
            "ccba_asno": ccba_asno,
            "ccba_ctcd": ccba_ctcd,
            "ccba_cpno": first(list_item.get("ccbaCpno"), detail.get("ccbaCpno")),
        },
        "names": {
            "ko": first(detail.get("ccbaMnm1"), list_item.get("ccbaMnm1"), "이름 미상"),
            "hanja": first(detail.get("ccbaMnm2"), list_item.get("ccbaMnm2")),
        },
        "classification": {
            "designation": first(detail.get("ccmaName"), list_item.get("ccmaName"), CATEGORY_LABELS.get(ccba_kdcd)),
            "gcode": detail.get("gcodeName"),
            "bcode": detail.get("bcodeName"),
            "mcode": detail.get("mcodeName"),
            "scode": detail.get("scodeName"),
        },
        "location": {
            "region": first(detail.get("ccbaCtcdNm"), list_item.get("ccbaCtcdNm"), REGION_LABELS.get(ccba_ctcd)),
            "district": first(detail.get("ccsiName"), list_item.get("ccsiName")),
            "address": address,
            "latitude": latitude,
            "longitude": longitude,
        },
        "period": {
            "era_text": first(detail.get("ccceName"), detail.get("ccbaAge")),
            "designated_date": detail.get("ccbaAsdt"),
        },
        "management": {
            "quantity": detail.get("ccbaQuan"),
            "owner": compact(detail.get("ccbaPoss")) or None,
            "manager": compact(first(detail.get("ccbaAdmin"), list_item.get("ccbaAdmin"))) or None,
            "cancelled": first(detail.get("ccbaCncl"), list_item.get("ccbaCncl")),
        },
        "media": {
            "image_url": detail.get("imageUrl") or None,
        },
        "description": {
            "source_text": content,
            "summary_v1": " ".join(split_sentences(content)[:3]),
        },
        "answer_facets": build_facets(content, address, latitude, longitude),
        "source": {
            "list_url": LIST_URL,
            "detail_url": source_url,
            "gis_location_url": GIS_LOCATION_URL,
            "event_url": EVENT_URL,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        },
        "raw": {
            "list": list_item,
            "detail": detail,
        },
    }


def normalize_event(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": item.get("seqNo"),
        "title": compact(item.get("subTitle")),
        "description": compact(item.get("subContent")),
        "start_date": item.get("sDate"),
        "end_date": item.get("eDate"),
        "date_text": compact(item.get("subDate")),
        "venue": compact(item.get("subDesc")),
        "region": compact(item.get("sido")),
        "district": compact(item.get("gugun")),
        "organizer": compact(item.get("groupName")),
        "contact": compact(item.get("contact")),
        "target": compact(item.get("subDesc_2")),
        "price": compact(item.get("subDesc_3")),
        "url": compact(item.get("subPath")),
        "source": "selectEventListOpenapi",
    }


def fetch_events(limit: int = 100) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    xml_text = fetch_xml(EVENT_URL, {"pageUnit": limit, "pageIndex": 1})
    return [normalize_event(item) for item in parse_items(xml_text)[:limit]]


def text_contains_any(text: str, terms: list[str]) -> bool:
    return any(term and term in text for term in terms)


def match_events(record: dict[str, Any], events: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    name = record["names"].get("ko") or ""
    short_terms = [part for part in re.split(r"\s+", name) if len(part) >= 2]
    region = compact(record["location"].get("region"))
    district = compact(record["location"].get("district"))
    matched: list[tuple[int, dict[str, Any]]] = []
    for event in events:
        haystack = " ".join(str(event.get(key) or "") for key in ["title", "description", "venue", "region", "district"])
        score = 0
        if name and name in haystack:
            score += 10
        if text_contains_any(haystack, short_terms):
            score += 5
        if region and region in compact(event.get("region")):
            score += 2
        if district and district in compact(event.get("district")):
            score += 3
        if score > 0:
            matched.append((score, event))
    return [event for _, event in sorted(matched, key=lambda item: -item[0])[:limit]]


def add_nearby_heritages(records: list[dict[str, Any]], radius_km_hint: float = 3.0, limit: int = 5) -> None:
    # Lightweight v1: use same district first, then same region. Precise distance sorting can be v2.
    for record in records:
        region = compact(record["location"].get("region"))
        district = compact(record["location"].get("district"))
        nearby = []
        for other in records:
            if other["id"] == record["id"]:
                continue
            other_region = compact(other["location"].get("region"))
            other_district = compact(other["location"].get("district"))
            score = 0
            if district and district == other_district:
                score += 10
            elif region and region == other_region:
                score += 3
            if score:
                nearby.append((score, {
                    "id": other["id"],
                    "name": other["names"].get("ko"),
                    "designation": other["classification"].get("designation"),
                    "region": other_region,
                    "district": other_district,
                    "address": other["location"].get("address"),
                    "latitude": other["location"].get("latitude"),
                    "longitude": other["location"].get("longitude"),
                    "match_basis": "same_district" if score >= 10 else "same_region",
                }))
        record["answer_facets"]["travel_visit"]["nearby_heritages"] = [item for _, item in sorted(nearby, key=lambda x: -x[0])[:limit]]


def add_events(records: list[dict[str, Any]], events: list[dict[str, Any]]) -> None:
    for record in records:
        record["answer_facets"]["travel_visit"]["events"] = match_events(record, events)


def fetch_xml(url: str, params: dict[str, Any]) -> str:
    full_url = f"{url}?{urlencode(params)}"
    request = Request(full_url, headers={"User-Agent": "heritage-rag-kakao-json-v1"})
    with urlopen(request, timeout=30) as response:  # noqa: S310 - trusted public OpenAPI URL set above
        return response.read().decode("utf-8", errors="replace")


def fetch_list(category: str, region: str, page_unit: int = 100) -> list[dict[str, Any]]:
    xml_text = fetch_xml(LIST_URL, {"ccbaKdcd": category, "ccbaCtcd": region, "pageUnit": page_unit, "pageIndex": 1})
    return parse_items(xml_text)


def fetch_detail(item: dict[str, Any]) -> dict[str, Any]:
    xml_text = fetch_xml(
        DETAIL_URL,
        {"ccbaKdcd": item.get("ccbaKdcd"), "ccbaAsno": item.get("ccbaAsno"), "ccbaCtcd": item.get("ccbaCtcd")},
    )
    items = parse_items(xml_text)
    return items[0] if items else {}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/heritage_v1_sample.json")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--categories", nargs="*", default=DEFAULT_CATEGORIES)
    parser.add_argument("--regions", nargs="*", default=DEFAULT_REGIONS)
    parser.add_argument("--event-limit", type=int, default=100, help="Number of KHS event records to fetch and match")
    args = parser.parse_args()

    records: list[dict[str, Any]] = []
    for region in args.regions:
        for category in args.categories:
            for list_item in fetch_list(category, region):
                if len(records) >= args.limit:
                    break
                detail = fetch_detail(list_item)
                records.append(normalize_record(list_item, detail))
            if len(records) >= args.limit:
                break
        if len(records) >= args.limit:
            break

    events = fetch_events(args.event_limit)
    add_nearby_heritages(records)
    add_events(records, events)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "heritage-chat.dataset.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(records),
        "enrichment": {
            "location_api": GIS_LOCATION_URL,
            "event_api": EVENT_URL,
            "event_count_fetched": len(events),
            "nearby_scope_v1": "same district first, then same region within generated dataset",
            "excluded_v1": ["traffic", "restaurants", "cafes", "non-heritage tourist spots"],
        },
        "records": records,
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "count": len(records)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
