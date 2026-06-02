"""
fetcher_search.py — 국가유산검색 API로 국가 종목 전체 수집

개선:
  - 종목별 중간 저장 (실패해도 이전 데이터 보존)
  - 이미 받은 ID는 건너뛰기 (resume)
  - 호출 실패 시 자동 재시도
  - 호출 간격 0.3초 (Rate Limiting 회피)

실행:
  python rag/fetcher_search.py           # 본 호출 (전체, 중간 저장)
  python rag/fetcher_search.py --test    # 테스트
  python rag/fetcher_search.py --kdcd 12 # 특정 종목만 (예: 보물)
"""
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import requests

LIST_URL = "http://www.khs.go.kr/cha/SearchKindOpenapiList.do"
DETAIL_URL = "http://www.khs.go.kr/cha/SearchKindOpenapiDt.do"

KDCD_LIST = [
    # 국가 종목 (이미 5,739개 수집 완료, resume 로직으로 자동 스킵)
    "11", "12", "13", "15", "16", "17", "18", "79",
    # 시도 종목 (신규, 약 11,710개)
    "21", "22", "23", "24", "31", "80",
]

KDCD_NAME = {
    "11": "국보",
    "12": "보물",
    "13": "사적",
    "14": "사적및명승",
    "15": "명승",
    "16": "천연기념물",
    "17": "국가무형문화재",
    "18": "국가민속문화재",
    "79": "국가등록문화재",
    # 시도 종목
    "21": "시도유형문화재",
    "22": "시도무형문화재",
    "23": "시도기념물",
    "24": "시도민속문화재",
    "31": "문화재자료",
    "80": "시도등록문화재",
}

PAGE_UNIT = 100
SLEEP_PER_CALL = 1.0      # 호출 간격 (Rate Limiting 회피, 0.3→1초로 증가)
SLEEP_PER_KDCD = 30       # 종목 사이 휴식 (10→30초로 증가)
MAX_RETRIES = 3           # 실패 시 재시도 횟수
RETRY_WAIT = 10           # 재시도 대기 시간 (5→10초로 증가)


def clean_text(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


# ─────────────────────────────────────────────────────────
# 재시도 로직이 포함된 GET
# ─────────────────────────────────────────────────────────
def safe_get(url: str) -> str:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, timeout=30)
            response.encoding = "utf-8"
            return response.text
        except Exception as e:
            if attempt < MAX_RETRIES:
                wait = RETRY_WAIT * attempt
                print(f"    ⚠ 호출 실패 ({attempt}/{MAX_RETRIES}), {wait}초 대기 후 재시도...")
                time.sleep(wait)
            else:
                raise


# ─────────────────────────────────────────────────────────
# 목록 호출 + 페이지네이션
# ─────────────────────────────────────────────────────────
def extract_ids(xml_str: str) -> tuple:
    root = ET.fromstring(xml_str)
    total = int(root.findtext("totalCnt") or 0)
    ids = []
    for item in root.iter("item"):
        kdcd = clean_text(item.findtext("ccbaKdcd") or "")
        asno = clean_text(item.findtext("ccbaAsno") or "")
        ctcd = clean_text(item.findtext("ccbaCtcd") or "")
        if kdcd and asno and ctcd:
            ids.append((kdcd, asno, ctcd))
    return total, ids


def fetch_all_ids_for_kdcd(kdcd: str) -> list:
    all_ids = []
    page = 1
    while True:
        url = f"{LIST_URL}?ccbaKdcd={kdcd}&pageUnit={PAGE_UNIT}&pageIndex={page}"
        xml_str = safe_get(url)
        total, ids = extract_ids(xml_str)
        if not ids:
            break
        all_ids.extend(ids)
        if len(all_ids) >= total:
            break
        page += 1
        if page > 100:
            break
        time.sleep(SLEEP_PER_CALL)
    return all_ids


# ─────────────────────────────────────────────────────────
# 상세 호출
# ─────────────────────────────────────────────────────────
def parse_detail_to_heritage(detail_root, kdcd, asno, ctcd):
    item = detail_root.find("item")
    if item is None:
        item = detail_root

    name = clean_text(item.findtext("ccbaMnm1") or "")
    description = clean_text(item.findtext("content") or "")
    era = clean_text(item.findtext("ccceName") or "")
    category = clean_text(item.findtext("ccmaName") or "")
    location = clean_text(item.findtext("ccbaLcad") or "")

    # 이름 없으면 메타데이터도 못 만듦 → 그것만 제외.
    # 50자 미만 필터는 indexer.py로 이동 (수집=raw 보존, 인덱싱 시 제외 — 정제 결정 ⑥)
    if not name:
        return None

    region = location.split()[0] if location else ""
    today = datetime.now().strftime("%Y-%m-%d")

    return {
        "id": f"K{kdcd}-{asno}",
        "name": name,
        "description": description,
        "era": era,
        "region": region,
        "category": category,
        "location": location,
        "image_url": "",
        "narration_url": "",
        "source_url": f"{DETAIL_URL}?ccbaKdcd={kdcd}&ccbaAsno={asno}&ccbaCtcd={ctcd}",
        "source_api": "국가유산청_검색_상세",
        "parent_id": None,
        "parent_name": None,
        "fetched_at": today,
    }


def fetch_detail_safe(kdcd, asno, ctcd):
    url = f"{DETAIL_URL}?ccbaKdcd={kdcd}&ccbaAsno={asno}&ccbaCtcd={ctcd}"
    xml_str = safe_get(url)
    return ET.fromstring(xml_str)


# ─────────────────────────────────────────────────────────
# heritages.json 입출력
# ─────────────────────────────────────────────────────────
def load_heritages(output_path: Path) -> list:
    if output_path.exists():
        with open(output_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_heritages(heritages: list, output_path: Path):
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(heritages, f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────────────────
# 테스트 모드
# ─────────────────────────────────────────────────────────
def test_mode():
    print("Test Mode: 국보 첫 페이지 호출")
    xml_str = safe_get(f"{LIST_URL}?ccbaKdcd=11&pageUnit={PAGE_UNIT}&pageIndex=1")
    total, ids = extract_ids(xml_str)
    print(f"전체 국보: {total}개 / 이번 페이지: {len(ids)}개")


# ─────────────────────────────────────────────────────────
# 한 종목 수집 (resume 지원)
# ─────────────────────────────────────────────────────────
def fetch_kdcd_with_resume(kdcd: str, existing_ids: set) -> list:
    print(f"\n[종목 {kdcd} = {KDCD_NAME[kdcd]}]")
    print(f"  목록 호출 중...")
    all_ids = fetch_all_ids_for_kdcd(kdcd)
    print(f"  → 전체 ID {len(all_ids)}개")

    # 이미 받은 것 제외
    todo = [(k, a, c) for k, a, c in all_ids if f"K{k}-{a}" not in existing_ids]
    skip = len(all_ids) - len(todo)
    if skip:
        print(f"  → 이미 받은 {skip}개 건너뜀, 신규 {len(todo)}개")

    print(f"  상세 호출 중...")
    new_heritages = []
    for i, (k, a, c) in enumerate(todo, 1):
        try:
            detail_root = fetch_detail_safe(k, a, c)
            h = parse_detail_to_heritage(detail_root, k, a, c)
            if h:
                new_heritages.append(h)
            if i % 100 == 0:
                print(f"    [{i}/{len(todo)}] 신규 수집 {len(new_heritages)}개")
            time.sleep(SLEEP_PER_CALL)
        except Exception as e:
            print(f"    ❌ ID K{k}-{a} 실패: {e}")

    print(f"  → 신규 본문 50자 이상: {len(new_heritages)}개")
    return new_heritages


# ─────────────────────────────────────────────────────────
# 본 호출 (중간 저장)
# ─────────────────────────────────────────────────────────
def main(kdcd_list=None):
    base = Path(__file__).parent.parent
    output_path = base / "data" / "heritages.json"

    if kdcd_list is None:
        kdcd_list = KDCD_LIST

    print("=" * 70)
    print(f"국가유산청 검색 API — {len(kdcd_list)}종 수집 (중간 저장 활성)")
    print(f"종목: {', '.join(KDCD_NAME[k] for k in kdcd_list)}")
    print("=" * 70)

    # 기존 데이터 로드 (resume용)
    heritages = load_heritages(output_path)
    print(f"\n현재 heritages.json: {len(heritages)}개")
    existing_ids = {h["id"] for h in heritages}

    start = time.time()
    for kdcd in kdcd_list:
        try:
            new_heritages = fetch_kdcd_with_resume(kdcd, existing_ids)
            heritages.extend(new_heritages)
            existing_ids.update(h["id"] for h in new_heritages)

            # 종목별 중간 저장 ⭐
            save_heritages(heritages, output_path)
            elapsed = (time.time() - start) / 60
            print(f"  💾 중간 저장 완료. 누적 {len(heritages)}개 / 소요 {elapsed:.1f}분")

            # 종목 사이 휴식
            if kdcd != kdcd_list[-1]:
                print(f"  ⏸ {SLEEP_PER_KDCD}초 휴식...")
                time.sleep(SLEEP_PER_KDCD)
        except Exception as e:
            print(f"\n❌ 종목 {kdcd} 처리 중 오류: {e}")
            print(f"  💾 현재까지 데이터는 이미 저장됨 ({len(heritages)}개)")
            print(f"  → 같은 명령으로 재실행하면 이어서 받을 수 있음")
            break

    print(f"\n✅ 완료. 총 {len(heritages)}개")
    print(f"  소요: {(time.time()-start)/60:.1f}분")

    print("\n다음 단계:")
    print("  Remove-Item -Recurse -Force chroma_db")
    print("  python rag/indexer.py")


if __name__ == "__main__":
    if "--test" in sys.argv:
        test_mode()
    elif "--kdcd" in sys.argv:
        idx = sys.argv.index("--kdcd")
        main([sys.argv[idx + 1]])
    else:
        main()
