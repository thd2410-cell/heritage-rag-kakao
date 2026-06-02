"""diagnose_single.py — single 질문 실패가 (a)검색 문제냐 (b)데이터 갭이냐 진단.

캐시(_emb_name.npz) 재사용 → 재임베딩 없음. 각 single 질문에 대해:
  - 검색: 정답 키워드가 top-3 검색결과 유산명에 있나? (hit/miss)
  - 데이터 존재: 정답 키워드가 heritages.json 전체 유산명에 있나? (present/absent)
  → miss+present = 검색 문제(retrieval로 개선 가능)
  → miss+absent  = 데이터 갭(수집해야 함, 검색 튜닝 무의미)

실행: python experiments/diagnose_single.py
"""
import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

BASE = Path(__file__).parent.parent


def main():
    cache = BASE / "experiments" / "_emb_name.npz"
    if not cache.exists():
        print("캐시(_emb_name.npz) 없음 — validate_bge_m3.py --with-name 먼저 실행 필요")
        return
    d = np.load(cache, allow_pickle=True)
    doc_emb, names = d["emb"], d["names"]
    print(f"캐시 로드: {len(doc_emb)} 청크")

    with open(BASE / "data" / "heritages.json", encoding="utf-8") as f:
        all_names = [h.get("name", "") for h in json.load(f)]
    with open(BASE / "experiments" / "testset.json", encoding="utf-8") as f:
        testset = json.load(f)

    model = SentenceTransformer("BAAI/bge-m3")

    singles = [q for q in testset if q.get("question_type") == "single" and q.get("expected_keywords")]
    hit = miss_present = miss_absent = 0
    miss_present_list, miss_absent_list = [], []

    for q in singles:
        expected = q["expected_keywords"]
        qv = model.encode([q["question"]], normalize_embeddings=True)[0].astype(np.float32)
        sims = doc_emb @ qv
        top3 = np.argsort(-sims)[:3]
        is_hit = any(kw in names[i] for kw in expected for i in top3)
        present = any(kw in nm for kw in expected for nm in all_names)

        if is_hit:
            hit += 1
        elif present:
            miss_present += 1
            miss_present_list.append((q["question"], expected))
        else:
            miss_absent += 1
            miss_absent_list.append((q["question"], expected))

    n = len(singles)
    print("\n" + "=" * 60)
    print(f"single 질문 {n}개 진단")
    print("=" * 60)
    print(f"  hit (top-3 적중):          {hit} ({hit/n:.0%})")
    print(f"  miss + 데이터에 있음(검색문제): {miss_present} ({miss_present/n:.0%})")
    print(f"  miss + 데이터에 없음(데이터갭): {miss_absent} ({miss_absent/n:.0%})")
    print("=" * 60)
    if miss_present_list:
        print("\n[검색 문제 — 데이터엔 있는데 못 찾음] → retrieval 개선 대상")
        for ques, exp in miss_present_list:
            print(f"  · {ques}  (정답:{exp})")
    if miss_absent_list:
        print("\n[데이터 갭 — 5743에 아예 없음] → 수집 대상")
        for ques, exp in miss_absent_list:
            print(f"  · {ques}  (정답:{exp})")


if __name__ == "__main__":
    main()
