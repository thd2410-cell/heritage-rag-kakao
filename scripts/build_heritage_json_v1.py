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
            "evidence": pick_sentences(sentences, TRAVEL_KEYWORDS),
            "nearby_places": [],
            "events": [],
            "status": "partial_v1",
            "note": "근처 여행지와 행사는 v2에서 위치정보/행사 API로 보강합니다.",
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
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        },
        "raw": {
            "list": list_item,
            "detail": detail,
        },
    }


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

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "heritage-chat.dataset.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(records),
        "records": records,
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "count": len(records)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
