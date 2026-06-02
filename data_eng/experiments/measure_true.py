"""measure_true.py — 고친 지표로 single 진짜 Recall (캐시 재사용, 즉시)

[발견 004] 수정: 검색 정답을 expected_keywords(본문단어) → 질문에서 추출한 유산명으로.
single 질문은 유산명이 질문에 들어있음("경복궁 쉽게 설명" → 경복궁).
벡터(name+content) 검색이 그 유산을 top-3에 가져오나 측정.

실행: python experiments/measure_true.py   (5743 name 캐시 사용)
"""
import json
import re
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

BASE = Path(__file__).parent.parent
PARTICLES = ("으로", "에서", "에게", "에는", "부터", "까지", "이랑", "와", "과", "은", "는", "이", "가", "을", "를", "에", "의", "도")
STOP = {"대해", "설명", "설명해줘", "쉽게", "심화", "자세", "알려줘", "해줘", "뭐야", "무엇", "퀴즈", "추천", "국가유산", "문화재", "문화유산", "유적", "유물", "누가", "언제", "어디", "어느", "시대", "역사", "만들", "지어", "왜", "뭐", "하는", "곳이야", "돼", "있어"}


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


def main():
    d = np.load(BASE / "experiments" / "_emb_name.npz", allow_pickle=True)
    doc_emb, names = d["emb"], d["names"]
    print(f"캐시(name, 5743): {len(doc_emb)} 청크")

    with open(BASE / "experiments" / "testset.json", encoding="utf-8") as f:
        testset = json.load(f)
    model = SentenceTransformer("BAAI/bge-m3")

    singles = [q for q in testset if q.get("question_type") == "single"]
    h3 = h5 = 0
    misses = []
    for q in singles:
        terms = query_terms(q["question"])
        qv = model.encode([q["question"]], normalize_embeddings=True)[0].astype(np.float32)
        sims = doc_emb @ qv
        top5 = np.argsort(-sims)[:5]
        rank = next((r for r, i in enumerate(top5, 1) if any(t in names[i] for t in terms)), None)
        if rank and rank <= 3:
            h3 += 1
        if rank and rank <= 5:
            h5 += 1
        if not (rank and rank <= 3):
            misses.append((q["question"], terms, [names[i] for i in top5[:3]]))

    n = len(singles)
    print("\n" + "=" * 60)
    print(f"single {n}개 — 고친 지표(질문 유산명 매칭), 벡터 name+content")
    print("=" * 60)
    print(f"  Recall@3: {h3/n:.0%}  ({h3}/{n})   [옛 깨진 지표: 57%]")
    print(f"  Recall@5: {h5/n:.0%}  ({h5}/{n})")
    print("=" * 60)
    if misses:
        print("\n[여전히 miss]")
        for ques, terms, top in misses:
            print(f"  · {ques}  terms={terms}  top3={top}")


if __name__ == "__main__":
    main()
