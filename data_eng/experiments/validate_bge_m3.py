"""validate_bge_m3.py — 도커/DB 없이 bge-m3 검색 품질 측정 (백엔드 형태 검증)

검색 품질은 임베딩(bge-m3)+거리(cosine)가 결정 → pgvector 없이 cosine 계산만으로 동일 측정.

모드:
  (기본)        content-only 벡터
  --with-name   유산명을 청크에 prepend (Exp-101)
  --hybrid      벡터 + 유산명 어휘매칭(백엔드 text 검색 모사) rerank (Exp-102)

임베딩 캐시: mode별로 _emb_*.npz 저장/재사용 (재실험 시 6분 임베딩 스킵). 데이터 바뀌면 캐시 삭제.
실행: python experiments/validate_bge_m3.py [--with-name] [--hybrid]
"""
import argparse
import json
import re
import statistics
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

BASE = Path(__file__).parent.parent
MIN_CONTENT = 50

_CJK = re.compile(r"[㐀-䶿一-鿿぀-ヿ]+")
_SPACES = re.compile(r"[ \t]{2,}")

# 백엔드 retrieval.py와 동일 개념의 쿼리 토큰화(조사 제거)
PARTICLES = ("으로", "에서", "에게", "에는", "부터", "까지", "이랑", "와", "과", "은", "는", "이", "가", "을", "를", "에", "의", "도")
STOP = {"대해", "설명", "설명해줘", "쉽게", "심화", "자세", "알려줘", "해줘", "뭐야", "무엇", "퀴즈", "추천", "국가유산", "문화재", "문화유산", "유적", "유물"}


def clean(text):
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = _CJK.sub("", text)
    text = re.sub(r"\(\s*\)", "", text)
    return _SPACES.sub(" ", text).strip()


def chunk(text, max_chars=800):
    text = (text or "").strip()
    if len(text) <= max_chars:
        return [text] if text else []
    return [text[i:i + max_chars] for i in range(0, len(text), max_chars)]


def query_terms(q):
    out = []
    for t in re.findall(r"[가-힣A-Za-z0-9]{2,}", q or ""):
        for p in PARTICLES:
            if t.endswith(p) and len(t) > len(p) + 1:
                t = t[: -len(p)]
                break
        if len(t) >= 2 and t not in STOP:
            out.append(t)
    return out


def build_embeddings(model, with_name):
    with open(BASE / "data" / "heritages.json", encoding="utf-8") as f:
        heritages = json.load(f)
    chunk_texts, chunk_names = [], []
    for h in heritages:
        name = h.get("name", "")
        content = clean(h.get("description"))
        if len(content) < MIN_CONTENT:
            continue
        for c in chunk(content):
            chunk_texts.append(f"유산명: {name}\n{c}" if with_name else c)
            chunk_names.append(name)
    print(f"  유산 {len(heritages)} → 임베딩 청크 {len(chunk_texts)}개")
    emb = np.asarray(model.encode(chunk_texts, normalize_embeddings=True,
                                  batch_size=64, show_progress_bar=True), dtype=np.float32)
    return emb, np.array(chunk_names, dtype=object)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-name", action="store_true", help="청크에 유산명 prepend (Exp-101)")
    parser.add_argument("--hybrid", action="store_true", help="벡터+유산명 어휘매칭 rerank (Exp-102)")
    args = parser.parse_args()
    mode = "name+content" if args.with_name else "content-only"

    print(f"bge-m3 로딩(GPU)... mode={mode} hybrid={args.hybrid}")
    model = SentenceTransformer("BAAI/bge-m3")
    print(f"  device={model.device}")

    cache = BASE / "experiments" / f"_emb_{'name' if args.with_name else 'content'}.npz"
    if cache.exists():
        d = np.load(cache, allow_pickle=True)
        doc_emb, names = d["emb"], d["names"]
        print(f"  캐시 로드: {len(doc_emb)} 청크 ({cache.name})")
    else:
        doc_emb, names = build_embeddings(model, args.with_name)
        np.savez(cache, emb=doc_emb, names=names)
        print(f"  캐시 저장: {cache.name}")

    with open(BASE / "experiments" / "testset.json", encoding="utf-8") as f:
        testset = json.load(f)

    recall3, recall5, rr, best_scores = [], [], [], []
    by_cat = {}
    for q in testset:
        expected = q.get("expected_keywords", [])
        cat = q.get("question_type", "single")
        if not expected:
            continue
        qv = model.encode([q["question"]], normalize_embeddings=True)[0].astype(np.float32)
        sims = doc_emb @ qv
        best_scores.append(float(sims[np.argmax(sims)]))

        if args.hybrid:
            terms = query_terms(q["question"])
            vec_top = list(np.argsort(-sims)[:20])
            name_hits = sorted((i for i in range(len(names)) if terms and any(t in names[i] for t in terms)),
                               key=lambda i: -sims[i])
            seen, order = set(), []
            for i in [*name_hits, *vec_top]:      # 이름매칭 먼저(벡터순), 그다음 벡터top
                if i not in seen:
                    seen.add(i)
                    order.append(i)
            top = order[:5]
        else:
            top = list(np.argsort(-sims)[:5])

        hit_rank = None
        for rank, idx in enumerate(top, 1):
            if any(kw in names[idx] for kw in expected):
                hit_rank = rank
                break
        recall3.append(1.0 if (hit_rank and hit_rank <= 3) else 0.0)
        recall5.append(1.0 if (hit_rank and hit_rank <= 5) else 0.0)
        rr.append(1.0 / hit_rank if hit_rank else 0.0)
        by_cat.setdefault(cat, []).append(1.0 if (hit_rank and hit_rank <= 3) else 0.0)

    def avg(xs):
        return sum(xs) / len(xs) if xs else 0.0

    tag = f"{mode}{' +hybrid' if args.hybrid else ''}"
    print("\n" + "=" * 60)
    print(f"bge-m3 검색 검증 (도커없음, vector{'+name' if args.hybrid else ''}) mode={tag}")
    print("=" * 60)
    print(f"  측정 문항:  {len(recall3)}개")
    print(f"  Recall@3:   {avg(recall3):.1%}   [content46.1 / name56.6 / 목표85]")
    print(f"  Recall@5:   {avg(recall5):.1%}")
    print(f"  MRR:        {avg(rr):.3f}")
    print("  카테고리별 Recall@3:")
    for c in ("single", "compare", "filter"):
        if c in by_cat:
            print(f"    {c:9s}: {avg(by_cat[c]):.1%}  (n={len(by_cat[c])})")
    if best_scores:
        print(f"  best cos: min {min(best_scores):.3f} / median {statistics.median(best_scores):.3f} / max {max(best_scores):.3f}")
    print("=" * 60)


if __name__ == "__main__":
    main()
