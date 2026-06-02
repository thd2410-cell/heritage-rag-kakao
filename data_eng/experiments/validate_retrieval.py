"""
validate_retrieval.py — cosine 수정 검증용 (검색 전용, GPT 호출 0)

목적: [발견 003] normalize + cosine 수정이 Recall@3를 회복시키는지 빠르게 확인.
      답변 생성(GPT) 없이 검색 단계만 측정 → 무료·빠름.

측정:
  - Recall@3 / Recall@5 (testset expected_keywords가 검색된 유산명에 있는가)
  - MRR
  - best_score 분포 (threshold 튜닝 근거 — cosine이면 0~2 범위여야 함)
  - 카테고리별 (single/compare/filter)

실행: python experiments/validate_retrieval.py
"""
import json
import statistics
from pathlib import Path

from langchain_community.vectorstores import Chroma
from langchain_core.embeddings import Embeddings
from sentence_transformers import SentenceTransformer

BASE = Path(__file__).parent.parent


# retriever.py / indexer.py와 동일한 임베딩 (normalize=True 필수)
class KoSimCSEEmbeddings(Embeddings):
    def __init__(self):
        print("임베딩 모델 로딩 중...")
        self.model = SentenceTransformer("BM-K/KoSimCSE-roberta")

    def embed_documents(self, texts):
        return self.model.encode(texts, normalize_embeddings=True).tolist()

    def embed_query(self, text):
        return self.model.encode([text], normalize_embeddings=True)[0].tolist()


def main():
    vectorstore = Chroma(
        persist_directory=str(BASE / "chroma_db"),
        embedding_function=KoSimCSEEmbeddings(),
        collection_name="heritages",
    )

    with open(Path(__file__).parent / "testset.json", "r", encoding="utf-8") as f:
        testset = json.load(f)

    k = 5
    recall3, recall5, rr = [], [], []
    best_scores = []
    by_cat = {}

    for q in testset:
        question = q["question"]
        expected = q.get("expected_keywords", [])
        cat = q.get("question_type", "single")
        if not expected:
            continue  # none 카테고리(정답 유산 없음)는 검색 recall 측정 제외

        docs_scores = vectorstore.similarity_search_with_score(question, k=k)
        if not docs_scores:
            recall3.append(0.0); recall5.append(0.0); rr.append(0.0)
            by_cat.setdefault(cat, []).append(0.0)
            continue

        best_scores.append(docs_scores[0][1])

        hit_rank = None
        for i, (doc, _) in enumerate(docs_scores, 1):
            name = doc.metadata.get("name", "")
            if any(kw in name for kw in expected):
                hit_rank = i
                break

        recall3.append(1.0 if (hit_rank and hit_rank <= 3) else 0.0)
        recall5.append(1.0 if (hit_rank and hit_rank <= 5) else 0.0)
        rr.append(1.0 / hit_rank if hit_rank else 0.0)
        by_cat.setdefault(cat, []).append(1.0 if (hit_rank and hit_rank <= 3) else 0.0)

    def avg(xs):
        return sum(xs) / len(xs) if xs else 0.0

    print("\n" + "=" * 60)
    print("검색 검증 결과 (cosine + normalize, 5743개)")
    print("=" * 60)
    print(f"  측정 문항:   {len(recall3)}개 (정답 유산 있는 것만)")
    print(f"  Recall@3:    {avg(recall3):.1%}   (옛 L2: 35.5%)")
    print(f"  Recall@5:    {avg(recall5):.1%}   (옛 L2: 38.2%)")
    print(f"  MRR:         {avg(rr):.3f}   (옛 L2: 0.309)")
    print("\n  카테고리별 Recall@3:")
    for cat in ("single", "compare", "filter"):
        if cat in by_cat:
            print(f"    {cat:10s}: {avg(by_cat[cat]):.1%}")
    if best_scores:
        print("\n  best_score 분포 (cosine이면 0~2 범위여야 정상):")
        print(f"    min {min(best_scores):.3f} / median {statistics.median(best_scores):.3f} / max {max(best_scores):.3f}")
        print(f"    → threshold 후보: median~max 사이 (예: {statistics.median(best_scores):.2f}~{max(best_scores):.2f})")
    print("=" * 60)


if __name__ == "__main__":
    main()
