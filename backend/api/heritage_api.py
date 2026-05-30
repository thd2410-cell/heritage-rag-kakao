"""국가유산청 Open API 호출 모듈.

국가유산청(구 문화재청)의 공개 API를 호출하여 국가유산 목록 검색과
상세 정보 조회를 수행한다. 인증 키 없이 호출 가능하며, 응답은 CDATA 섹션을
포함한 XML이다. xml.etree.ElementTree 로 파싱한다.

파이프라인 1~2단계 담당:
  1단계: search_heritage()  -> 유산 이름으로 검색하여 식별자 추출
  2단계: get_heritage_detail() -> content(해설 원문), imageUrl 추출
"""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional

import requests

# 국가유산청 Open API 엔드포인트
LIST_API_URL = "http://www.khs.go.kr/cha/SearchKindOpenapiList.do"
DETAIL_API_URL = "http://www.khs.go.kr/cha/SearchKindOpenapiDt.do"

# 네트워크 타임아웃(초)
DEFAULT_TIMEOUT = 20


@dataclass
class HeritageItem:
    """목록 API 검색 결과 1건. 상세 조회에 필요한 식별자를 담는다."""

    ccbaMnm1: str = ""        # 한글 명칭 (예: 서울 숭례문)
    ccbaMnm2: str = ""        # 한자 명칭 (예: 서울 崇禮門)
    ccbaCpno: str = ""        # 문화재 고유번호
    ccbaKdcd: str = ""        # 종목 코드 (11=국보, 12=보물 ...)
    ccbaCtcd: str = ""        # 지역 코드
    ccbaAsno: str = ""        # 관리번호 (상세 조회 키)
    ccmaName: str = ""        # 종목명 (예: 국보)
    ccbaCtcdNm: str = ""      # 지역명 (예: 서울)
    ccsiName: str = ""        # 시군구명
    longitude: Optional[float] = None
    latitude: Optional[float] = None


@dataclass
class HeritageDetail:
    """상세 API 응답. 해설 원문(content)과 대표 이미지를 포함한다."""

    ccbaMnm1: str = ""        # 한글 명칭
    ccbaMnm2: str = ""        # 한자 명칭
    content: str = ""         # 한국어 해설 원문 ← 핵심
    imageUrl: str = ""        # 대표 이미지 URL
    ccceName: str = ""        # 시대 정보 (예: 조선 태조 7년(1398))
    gcodeName: str = ""       # 대분류
    bcodeName: str = ""       # 중분류
    ccbaLcad: str = ""        # 소재지 주소
    ccmaName: str = ""        # 종목명 (예: 국보)
    # 조회에 사용한 식별자 (디버깅/연계용)
    ccbaKdcd: str = ""
    ccbaAsno: str = ""
    ccbaCtcd: str = ""


class HeritageAPIError(Exception):
    """국가유산청 API 호출/파싱 실패."""


def _fetch_xml(
    url: str, params: dict, timeout: int = DEFAULT_TIMEOUT, *, max_retry: int = 3
) -> ET.Element:
    """API를 호출하고 XML 루트 엘리먼트를 반환한다.

    khs.go.kr 서버가 간헐적으로 연결을 거부(WinError 10061)하거나 타임아웃되므로
    연결/타임아웃 오류는 지수 백오프로 재시도한다.
    """
    delay = 1.0
    last_exc: Optional[Exception] = None
    for attempt in range(max_retry + 1):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            # 응답은 utf-8 XML. requests가 인코딩을 잘못 추론할 수 있으므로 명시.
            resp.encoding = "utf-8"
            try:
                return ET.fromstring(resp.text)
            except ET.ParseError as exc:
                raise HeritageAPIError(f"XML 파싱 실패: {url} ({exc})") from exc
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            if attempt < max_retry:
                time.sleep(delay)
                delay *= 2
                continue
        except requests.RequestException as exc:
            raise HeritageAPIError(f"API 요청 실패: {url} ({exc})") from exc
    raise HeritageAPIError(f"API 요청 실패(재시도 초과): {url} ({last_exc})")


def _text(element: Optional[ET.Element], tag: str, default: str = "") -> str:
    """자식 태그의 텍스트를 추출하고 앞뒤 공백/내부 줄바꿈을 정리한다.

    ccbaLcad 처럼 CDATA 내부에 불필요한 줄바꿈/들여쓰기가 섞인 필드를
    안전하게 정규화한다.
    """
    if element is None:
        return default
    child = element.find(tag)
    if child is None or child.text is None:
        return default
    # 연속 공백/줄바꿈을 단일 공백으로 축약 (단, content는 줄바꿈 보존 위해 별도 처리)
    return child.text.strip()


def _content_text(element: Optional[ET.Element], tag: str) -> str:
    """해설 원문(content)용 텍스트 추출. 문단 줄바꿈은 보존하되 양끝만 정리."""
    if element is None:
        return ""
    child = element.find(tag)
    if child is None or child.text is None:
        return ""
    return child.text.strip()


def _to_float(value: str) -> Optional[float]:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    # 좌표가 없는 항목은 0 으로 내려옴 -> None 처리
    return f if f != 0 else None


def search_heritage(
    name: str,
    *,
    ccba_kdcd: Optional[str] = None,
    page_unit: int = 10,
    page_index: int = 1,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[HeritageItem]:
    """유산 이름으로 목록 API를 검색한다. (파이프라인 1단계)

    Args:
        name: 검색할 유산 한글 이름 (예: "숭례문").
        ccba_kdcd: 종목 코드로 결과를 좁히려면 지정 (11=국보 등). 기본 전체.
        page_unit: 페이지당 건수.
        page_index: 페이지 번호.

    Returns:
        검색된 HeritageItem 목록 (정확도순, API 정렬 순서 유지).
    """
    params = {
        "ccbaMnm1": name,
        "pageUnit": page_unit,
        "pageIndex": page_index,
    }
    if ccba_kdcd:
        params["ccbaKdcd"] = ccba_kdcd

    root = _fetch_xml(LIST_API_URL, params, timeout)

    items: list[HeritageItem] = []
    for item in root.findall("item"):
        items.append(
            HeritageItem(
                ccbaMnm1=_text(item, "ccbaMnm1"),
                ccbaMnm2=_text(item, "ccbaMnm2"),
                ccbaCpno=_text(item, "ccbaCpno"),
                ccbaKdcd=_text(item, "ccbaKdcd"),
                ccbaCtcd=_text(item, "ccbaCtcd"),
                ccbaAsno=_text(item, "ccbaAsno"),
                ccmaName=_text(item, "ccmaName"),
                ccbaCtcdNm=_text(item, "ccbaCtcdNm"),
                ccsiName=_text(item, "ccsiName"),
                longitude=_to_float(_text(item, "longitude")),
                latitude=_to_float(_text(item, "latitude")),
            )
        )
    return items


def list_heritages(
    ccba_kdcd: str = "11",
    *,
    page_unit: int = 30,
    page_index: int = 1,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[HeritageItem]:
    """이름 없이 종목 코드로 유산 목록을 가져온다. (대량 적재용)

    Args:
        ccba_kdcd: 종목 코드 (11=국보, 12=보물, 13=사적 ...).
        page_unit: 가져올 건수.
        page_index: 페이지 번호.
    """
    # 이름 검색 없이 종목 코드만으로 목록 조회 (ccbaMnm1 생략)
    return search_heritage(
        "", ccba_kdcd=ccba_kdcd, page_unit=page_unit, page_index=page_index, timeout=timeout
    )


def get_heritage_detail(
    ccba_kdcd: str,
    ccba_asno: str,
    ccba_ctcd: str,
    *,
    timeout: int = DEFAULT_TIMEOUT,
) -> HeritageDetail:
    """식별자로 상세 API를 호출해 해설 원문/이미지를 조회한다. (파이프라인 2단계)

    Args:
        ccba_kdcd: 종목 코드.
        ccba_asno: 관리번호.
        ccba_ctcd: 지역 코드.

    Returns:
        HeritageDetail (content, imageUrl 등 포함).
    """
    params = {
        "ccbaKdcd": ccba_kdcd,
        "ccbaAsno": ccba_asno,
        "ccbaCtcd": ccba_ctcd,
    }
    root = _fetch_xml(DETAIL_API_URL, params, timeout)

    item = root.find("item")
    if item is None:
        raise HeritageAPIError(
            f"상세 정보를 찾을 수 없습니다 "
            f"(ccbaKdcd={ccba_kdcd}, ccbaAsno={ccba_asno}, ccbaCtcd={ccba_ctcd})"
        )

    # ccbaLcad 는 CDATA 내부에 줄바꿈/들여쓰기가 많아 공백 정규화
    lcad_raw = _text(item, "ccbaLcad")
    lcad = re.sub(r"\s+", " ", lcad_raw).strip()

    return HeritageDetail(
        ccbaMnm1=_text(item, "ccbaMnm1"),
        ccbaMnm2=_text(item, "ccbaMnm2"),
        content=_content_text(item, "content"),
        imageUrl=_text(item, "imageUrl"),
        ccceName=_text(item, "ccceName"),
        gcodeName=_text(item, "gcodeName"),
        bcodeName=_text(item, "bcodeName"),
        ccbaLcad=lcad,
        ccmaName=_text(item, "ccmaName"),
        ccbaKdcd=ccba_kdcd,
        ccbaAsno=ccba_asno,
        ccbaCtcd=ccba_ctcd,
    )


def search_and_get_detail(
    name: str,
    *,
    ccba_kdcd: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Optional[HeritageDetail]:
    """이름 검색 후 첫 번째(가장 관련성 높은) 결과의 상세를 조회하는 편의 함수.

    검색 결과가 없으면 None을 반환한다.
    """
    results = search_heritage(name, ccba_kdcd=ccba_kdcd, timeout=timeout)
    if not results:
        return None
    top = results[0]
    return get_heritage_detail(
        top.ccbaKdcd, top.ccbaAsno, top.ccbaCtcd, timeout=timeout
    )


if __name__ == "__main__":
    # 숭례문으로 목록 -> 상세 호출 테스트
    print("=" * 60)
    print("[1단계] 목록 API 검색: '숭례문'")
    print("=" * 60)
    found = search_heritage("숭례문", page_unit=5)
    for i, it in enumerate(found, 1):
        print(f"{i}. {it.ccbaMnm1} ({it.ccbaMnm2}) | {it.ccmaName} "
              f"| kdcd={it.ccbaKdcd} asno={it.ccbaAsno} ctcd={it.ccbaCtcd}")

    if not found:
        print("검색 결과가 없습니다.")
        raise SystemExit(1)

    target = found[0]
    print()
    print("=" * 60)
    print(f"[2단계] 상세 API 조회: {target.ccbaMnm1}")
    print("=" * 60)
    detail = get_heritage_detail(
        target.ccbaKdcd, target.ccbaAsno, target.ccbaCtcd
    )
    print(f"명칭     : {detail.ccbaMnm1} ({detail.ccbaMnm2})")
    print(f"종목     : {detail.ccmaName} / {detail.gcodeName} > {detail.bcodeName}")
    print(f"시대     : {detail.ccceName}")
    print(f"소재지   : {detail.ccbaLcad}")
    print(f"이미지   : {detail.imageUrl}")
    print(f"해설 원문 (앞 200자):")
    print(f"  {detail.content[:200]}...")
    print()
    print(f"[OK] content 길이: {len(detail.content)}자")
