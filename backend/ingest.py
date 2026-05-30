"""국가유산 원문 + 용어 사전을 청크·임베딩하여 pgvector에 적재한다.

실행 (backend/ 디렉터리에서):
    python ingest.py                      # 기본 유산 + 용어 전체 적재(테이블 초기화)
    python ingest.py 숭례문 불국사          # 지정 유산만 추가 적재

파이프라인 2단계(벡터 DB 구성):
  - content를 문단 기준 300자 청크로 분할
  - 각 청크를 임베딩해 pgvector에 저장
  - 용어 사전도 함께 임베딩해 저장
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from api.embeddings import embed_dim, embed_info, embed_texts
from api.heritage_api import (
    HeritageDetail,
    get_heritage_detail,
    list_heritages,
    search_and_get_detail,
)
from core import vector_store
from core.chunker import chunk_text
from core.term_extractor import get_default_dictionary

# 테스트 시나리오용 기본 유산
DEFAULT_HERITAGES = ["숭례문", "원각사지 십층석탑"]


def _embed_and_records(texts: list[str], meta_list: list[dict]) -> list[dict]:
    """텍스트들을 임베딩하고 메타와 합쳐 insert용 레코드를 만든다."""
    vectors = embed_texts(texts)
    records = []
    for vec, meta in zip(vectors, meta_list):
        records.append({**meta, "embedding": vec})
    return records


def _store_detail(detail: HeritageDetail) -> int:
    """HeritageDetail을 청크→임베딩→저장. 적재된 청크 수 반환."""
    hname = detail.ccbaMnm1
    # 메타 헤더 청크 (기본 정보 — 비교/사실 질의에 도움)
    header = (
        f"[유산 정보] {hname} ({detail.ccbaMnm2}). 종목: {detail.ccmaName}. "
        f"시대: {detail.ccceName}. 분류: {detail.gcodeName} > {detail.bcodeName}. "
        f"소재지: {detail.ccbaLcad}."
    )
    chunks = [header] + chunk_text(detail.content, max_len=300)
    category = detail.bcodeName or detail.gcodeName or None  # 개인화 가중치용 분류
    meta_list = [
        {
            "source_type": "heritage",
            "heritage_name": hname,
            "term": None,
            "chunk_index": i,
            "content": c,
            "image_url": detail.imageUrl or None,
            "category": category,
        }
        for i, c in enumerate(chunks)
    ]
    records = _embed_and_records(chunks, meta_list)
    n = vector_store.insert_chunks(records)
    print(f"  + {hname}: {n}개 청크 적재")
    return n


def ingest_heritage(name: str) -> int:
    """유산 이름 1건을 조회→저장. 적재된 청크 수 반환."""
    detail = search_and_get_detail(name)
    if detail is None or not detail.content:
        print(f"  ! '{name}' 원문을 찾지 못해 건너뜀")
        return 0
    return _store_detail(detail)


def ingest_bulk(ccba_kdcd: str, count: int) -> int:
    """종목 코드로 목록을 가져와 다량 적재한다 (이미 적재된 유산은 건너뜀)."""
    items = list_heritages(ccba_kdcd, page_unit=count, page_index=1)
    existing = vector_store.existing_heritage_names()
    total = 0
    print(f"  목록 {len(items)}건 (종목 {ccba_kdcd}), 기적재 {len(existing)}건 제외")
    for it in items:
        if it.ccbaMnm1 in existing:
            continue
        try:
            detail = get_heritage_detail(it.ccbaKdcd, it.ccbaAsno, it.ccbaCtcd)
        except Exception as exc:
            print(f"  ! {it.ccbaMnm1} 상세 조회 실패: {exc}")
            continue
        if not detail.content:
            continue
        total += _store_detail(detail)
        existing.add(it.ccbaMnm1)
    return total


def ingest_terms() -> int:
    """용어 사전 전체를 임베딩해 저장. 적재된 용어 수 반환."""
    d = get_default_dictionary()
    items = [(term, d.get(term)) for term in d._terms]  # noqa: SLF001
    texts = [f"{term}: {definition}" for term, definition in items]
    meta_list = [
        {
            "source_type": "term",
            "heritage_name": None,
            "term": term,
            "chunk_index": 0,
            "content": text,
        }
        for (term, _), text in zip(items, texts)
    ]
    # 임베딩 호출 수가 많을 수 있어 진행 표시
    print(f"  용어 {len(texts)}개 임베딩 중...")
    records = _embed_and_records(texts, meta_list)
    n = vector_store.insert_chunks(records)
    print(f"  + 용어 사전: {n}개 적재")
    return n


def backfill_images() -> int:
    """이미지 URL이 비어 있는 기존 유산들의 image_url을 상세 API로 채운다."""
    names = sorted(vector_store.existing_heritage_names())
    filled = 0
    for name in names:
        if vector_store.heritage_image(name):
            continue  # 이미 있음
        try:
            detail = search_and_get_detail(name)
        except Exception as exc:
            print(f"  ! {name} 조회 실패: {exc}")
            continue
        if detail and detail.imageUrl:
            n = vector_store.set_heritage_image(name, detail.imageUrl)
            filled += 1
            print(f"  + {name}: 이미지 적용({n}행)")
        else:
            print(f"  - {name}: 이미지 없음")
    return filled


def ingest_notes() -> int:
    """검증된 지식 메모(data/knowledge_notes.json)를 임베딩해 적재한다.

    국가유산청 원문에 없는 '검증된 외부 사실'(예: 명칭 유래 낭설 바로잡기)을
    source_type='note' 로 넣어, 관련 유산 질문 시 근거로 함께 검색되게 한다.
    """
    path = Path(__file__).resolve().parent / "data" / "knowledge_notes.json"
    if not path.exists():
        print("  - knowledge_notes.json 없음, 건너뜀")
        return 0
    with open(path, encoding="utf-8") as f:
        notes = json.load(f)

    vector_store.delete_by_source_type("note")  # 재적재 시 중복 방지
    texts: list[str] = []
    metas: list[dict] = []
    for note in notes:
        body = f"[{note['title']}] {note['text']}"
        # 출처(URL)는 임베딩 본문에 넣지 않고, 저장 내용 끝에 마커로 붙여 둔다.
        # (응답 시 분리해 '근거 원문'의 클릭 링크로 노출)
        refs = note.get("sources") or []
        stored = body
        if refs:
            stored = body + "\n[[SOURCES]]" + json.dumps(refs, ensure_ascii=False)
        metas.append(
            {
                "source_type": "note",
                "heritage_name": note.get("heritage"),
                "term": None,
                "chunk_index": 0,
                "content": stored,
                "image_url": None,
                "category": None,
            }
        )
        texts.append(body)  # 임베딩은 깨끗한 본문으로
    if not texts:
        return 0
    records = _embed_and_records(texts, metas)
    n = vector_store.insert_chunks(records)
    print(f"  + 지식 메모: {n}개 청크 적재")
    return n


def backfill_categories() -> int:
    """기존 청크의 category를, 이미 저장된 헤더 청크의 '분류: X > Y' 에서 파싱해 채운다.

    API 호출/임베딩 없이 DB 안에서만 처리한다.
    """
    import re

    filled = 0
    for name, content in vector_store.heritage_headers():
        m = re.search(r"분류:\s*[^>]+>\s*([^.]+?)\s*\.", content)
        category = m.group(1).strip() if m else None
        if not category:
            # '분류: X.' 처럼 대분류만 있는 경우
            m2 = re.search(r"분류:\s*([^.>]+?)\s*\.", content)
            category = m2.group(1).strip() if m2 else None
        if category:
            vector_store.set_category(name, category)
            filled += 1
            print(f"  + {name}: {category}")
    return filled


def main(argv: list[str]) -> None:
    print(f"[임베딩] {embed_info()}")
    if not vector_store.ping():
        print("! pgvector 연결 실패 — docker compose up -d 로 DB를 먼저 띄우세요.")
        raise SystemExit(1)

    # 사용법:
    #   python ingest.py                  -> 초기화 + 용어 + 기본 유산 적재
    #   python ingest.py 불국사 석굴암       -> 지정 유산 추가 적재
    #   python ingest.py --bulk            -> 국보 30건 추가 적재 (기적재 제외)
    #   python ingest.py --bulk 11 50      -> 종목 11(국보) 50건 추가 적재
    args = argv[1:]

    if args and args[0] == "--notes":
        vector_store.ensure_schema(embed_dim())
        print("[적재] 검증된 지식 메모")
        ingest_notes()
        return

    if args and args[0] == "--backfill-categories":
        vector_store.ensure_schema(embed_dim())
        print("[백필] 기존 유산 category(bcodeName) 채우기")
        n = backfill_categories()
        print(f"[완료] {n}종 분류 적용")
        return

    if args and args[0] == "--backfill-images":
        vector_store.ensure_schema(embed_dim())
        print("[백필] 기존 유산 이미지 URL 채우기")
        n = backfill_images()
        print(f"[완료] {n}종 이미지 적용")
        return

    if args and args[0] == "--bulk":
        kdcd = args[1] if len(args) > 1 else "11"
        count = int(args[2]) if len(args) > 2 else 30
        vector_store.ensure_schema(embed_dim())
        print(f"[대량 적재] 종목={kdcd} 최대 {count}건")
        ingest_bulk(kdcd, count)
    elif args:
        vector_store.ensure_schema(embed_dim())
        print(f"[적재] 유산: {', '.join(args)}")
        for name in args:
            ingest_heritage(name)
    else:
        print(f"[스키마] 초기화 (vector dim={embed_dim()})")
        vector_store.reset_schema(embed_dim())
        print("[적재] 용어 사전")
        ingest_terms()
        print("[적재] 검증된 지식 메모")
        ingest_notes()
        print(f"[적재] 유산: {', '.join(DEFAULT_HERITAGES)}")
        for name in DEFAULT_HERITAGES:
            ingest_heritage(name)

    print("\n[완료] 저장 현황:")
    st = vector_store.stats()
    print(f"  총 {st['total']}개 청크")
    print(f"  유형별: {st['by_type']}")
    print(f"  유산별 {len(st['by_heritage'])}종: {list(st['by_heritage'])}")


if __name__ == "__main__":
    main(sys.argv)
