"""proper_eval.py — 고친 지표로 single/compare 진짜 Recall (캐시 재사용).

[발견 004] 수정판: expected_heritage(정답 유산) 기준 채점 + 정규화(띄어쓰기)·별칭.
single: 정답 유산이 top-3에 있나(Recall@3).
compare: 정답 유산들이 top-k에 다 있나(엔티티 recall@5/@10, 전부적중률).

전제: _emb_name.npz 캐시(5743) + testset에 expected_heritage(add_expected_heritage.py 먼저).
실행: python experiments/proper_eval.py
"""
import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

BASE = Path(__file__).parent.parent
ALIAS = {"석가탑": "삼층석탑"}  # 별칭(석가탑=불국사 삼층석탑)


def matches(expected, name):
    e, r = expected.replace(" ", ""), name.replace(" ", "")
    if e in r or r in e:
        return True
    if expected in ALIAS and ALIAS[expected].replace(" ", "") in r:
        return True
    return False


def main():
    d = np.load(BASE / "experiments" / "_emb_name.npz", allow_pickle=True)
    doc_emb, names = d["emb"], d["names"]
    print(f"캐시(name, 5743): {len(doc_emb)} 청크")
    testset = json.load(open(BASE / "experiments" / "testset.json", encoding="utf-8"))
    model = SentenceTransformer("BAAI/bge-m3")

    def retrieve(question, k):
        # 결함#1 수정: top-k "청크"가 아니라 top-k "유산"(중복 유산명 제거)
        qv = model.encode([question], normalize_embeddings=True)[0].astype(np.float32)
        sims = doc_emb @ qv
        seen, out = set(), []
        for i in np.argsort(-sims):
            nm = names[i]
            if nm not in seen:
                seen.add(nm)
                out.append(nm)
            if len(out) >= k:
                break
        return out

    # single
    singles = [q for q in testset if q["question_type"] == "single" and q.get("expected_heritage")]
    s_hit, s_miss = 0, []
    for q in singles:
        exp = q["expected_heritage"][0]
        top3 = retrieve(q["question"], 3)
        if any(matches(exp, nm) for nm in top3):
            s_hit += 1
        else:
            s_miss.append((q["question"], exp, retrieve(q["question"], 3)))

    # compare
    compares = [q for q in testset if q["question_type"] == "compare" and q.get("expected_heritage")]
    ent_r5, ent_r10, all5 = [], [], 0
    for q in compares:
        exps = q["expected_heritage"]
        top10 = retrieve(q["question"], 10)
        top5 = top10[:5]
        found5 = sum(1 for e in exps if any(matches(e, nm) for nm in top5))
        found10 = sum(1 for e in exps if any(matches(e, nm) for nm in top10))
        ent_r5.append(found5 / len(exps))
        ent_r10.append(found10 / len(exps))
        if found5 == len(exps):
            all5 += 1

    # none: 정답이 "유산"이 아님 → best 유사도가 낮아 거절돼야 함
    def best_sim(question):
        qv = model.encode([question], normalize_embeddings=True)[0].astype(np.float32)
        return float(np.max(doc_emb @ qv))

    none_q = [q for q in testset if q["question_type"] == "none"]
    none_scores = [(q["sub_type"], best_sim(q["question"])) for q in none_q]
    single_best = [best_sim(q["question"]) for q in singles]

    def avg(xs):
        return sum(xs) / len(xs) if xs else 0.0

    print("\n" + "=" * 60)
    print("고친 지표 (expected_heritage 기준, 정규화+별칭)")
    print("=" * 60)
    print(f"[single] {len(singles)}문항")
    print(f"  Recall@3: {s_hit/len(singles):.0%}  ({s_hit}/{len(singles)})   [옛 깨진지표 57%]")
    print(f"[compare] {len(compares)}문항")
    print(f"  엔티티 Recall@5:  {avg(ent_r5):.0%}   (정답유산 중 top-5에 든 비율)")
    print(f"  엔티티 Recall@10: {avg(ent_r10):.0%}")
    print(f"  전부적중@5:       {all5/len(compares):.0%}  ({all5}/{len(compares)})")
    print(f"[none] {len(none_q)}문항 — best 유사도(낮을수록 거절돼야 정상)")
    print(f"  single best 유사도 평균: {avg(single_best):.3f} (min {min(single_best):.3f})")
    for sub in ("overseas", "out_of_topic", "out_of_data"):
        ss = [s for st, s in none_scores if st == sub]
        if ss:
            print(f"  none/{sub:12s}: 평균 {avg(ss):.3f} / 최대 {max(ss):.3f}")
    # 임계값 후보: single 최소와 none 최대 사이
    none_max = max(s for _, s in none_scores)
    print(f"  → threshold 후보: none최대 {none_max:.3f} ~ single최소 {min(single_best):.3f} 사이")
    print("=" * 60)
    if s_miss:
        print("\n[single 여전히 miss]")
        for ques, exp, top in s_miss:
            print(f"  · {ques}  정답={exp}  top3={top}")


if __name__ == "__main__":
    main()
