"""
evaluate.py — testset.json 자동 평가 → runs.csv 한 줄 추가

실행:
  python experiments/evaluate.py                                                # 기본 평가만
  python experiments/evaluate.py --exp-id Exp-100d --llm-judge --note "베이스라인"   ⭐
  python experiments/evaluate.py --exp-id Exp-102 --llm-judge --top-k 5 --note "Top-K 5"
  python experiments/evaluate.py --exp-id Exp-103 --llm-judge --prompt-version v2 --note "프롬프트 v2"
  python experiments/evaluate.py --llm-judge --sample 20                       # 빠른 테스트

옵션:
  --exp-id          실험 ID (예: Exp-100d). 미지정 시 타임스탬프 자동.
  --note            실험 메모
  --llm-judge       LLM-as-judge 평가 추가 (GPT-4o-mini 4지표)
  --top-k           검색 chunk 수 (기본 3)
  --prompt-version  시스템 프롬프트 버전 (v1=기본 / v2=환각 강화)
  --sample N        N문항만 (빠른 테스트)

기능:
1. testset.json 로드
2. 각 질문에 대해 retriever 답변 생성
3. 자동 채점 (키워드 기반):
   - 정확도, no-answer, 출처, 시간, 길이
4. 검색 품질 측정 (Recall@K, MRR)
5. (옵션) LLM-as-judge 4지표 — GPT-4o-mini
   - Faithfulness (환각)
   - Answer Relevancy (동문서답)
   - Context Precision (검색 정밀도)
   - Context Recall (검색 재현율)
6. runs.csv 한 줄 추가
7. results/Exp-XXX.json 상세 결과 저장
"""
import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

from rag.retriever import answer_with_context, vectorstore, client as openai_client  # noqa: E402


DEFAULT_CONFIG = {
    "prompt_version": "v1",
    "embedding_model": "KoSimCSE-roberta",
    "llm_model": "gpt-4o-mini",
    "temperature": 0.0,
    "chunk_size": 400,
    "chunk_overlap": 50,
    "top_k": 3,
    "dataset_version": "heritages-v3-627items",
}


# ─────────────────────────────────────────────────────────
# Stage 6: 검색 품질 측정 (Recall@K, MRR)
# ─────────────────────────────────────────────────────────
def measure_retrieval(question: str, expected_keywords: list, k: int = 3) -> dict:
    """정답 chunk = metadata.name에 expected_keywords 중 하나가 포함된 chunk"""
    if not expected_keywords:
        return {"recall_at_k": None, "rank": None, "rr": None}

    docs = vectorstore.similarity_search(question, k=k)
    for i, doc in enumerate(docs, 1):
        name = doc.metadata.get("name", "")
        if any(kw in name for kw in expected_keywords):
            return {"recall_at_k": 1.0, "rank": i, "rr": 1.0 / i}

    return {"recall_at_k": 0.0, "rank": None, "rr": 0.0}


# ─────────────────────────────────────────────────────────
# LLM-as-judge (GPT-4o-mini) — RAGAS 대체
# 4지표 한 번에 평가 (토큰 절약)
# ─────────────────────────────────────────────────────────
JUDGE_PROMPT = """당신은 RAG 시스템 평가 전문가입니다.
다음 답변을 4개 지표로 0.0~1.0 점수 평가하세요.

[참고 자료]
{context}

[질문]
{question}

[답변]
{answer}

[평가 지표]
1. faithfulness: 답변이 참고 자료에 근거하는가? (자료에 없는 내용 = 환각)
2. answer_relevancy: 답변이 질문에 적합한가? (동문서답 X)
3. context_precision: 참고 자료가 답변에 실제 쓸모 있는가?
4. context_recall: 답변에 필요한 정보가 참고 자료에 충분한가?

JSON만 출력:
{{"faithfulness": 0.0, "answer_relevancy": 0.0, "context_precision": 0.0, "context_recall": 0.0}}"""


def llm_judge_one(question: str, answer: str, contexts: list) -> dict:
    """단일 답변 → 4지표 점수"""
    if not answer or not contexts:
        return {k: None for k in ("faithfulness", "answer_relevancy", "context_precision", "context_recall")}

    context_text = "\n\n---\n\n".join(contexts)[:3000]
    prompt = JUDGE_PROMPT.format(context=context_text, question=question, answer=answer)

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=150,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        scores = json.loads(response.choices[0].message.content)
        return {
            "faithfulness": max(0, min(1, float(scores.get("faithfulness", 0)))),
            "answer_relevancy": max(0, min(1, float(scores.get("answer_relevancy", 0)))),
            "context_precision": max(0, min(1, float(scores.get("context_precision", 0)))),
            "context_recall": max(0, min(1, float(scores.get("context_recall", 0)))),
        }
    except Exception as e:
        return {k: None for k in ("faithfulness", "answer_relevancy", "context_precision", "context_recall")}


def run_llm_judge(results: list) -> dict:
    """전체 결과 LLM-as-judge → 평균"""
    print("\n🧪 LLM-as-judge 평가 시작 (GPT-4o-mini)")
    valid = [r for r in results if not r["error"] and r["answer"]]
    if not valid:
        print("  ❌ 평가 가능한 결과 없음")
        return None
    print(f"  📋 평가 대상: {len(valid)}개")

    sums = {k: [] for k in ("faithfulness", "answer_relevancy", "context_precision", "context_recall")}
    for i, r in enumerate(valid, 1):
        scores = llm_judge_one(r["question"], r["answer"], r["contexts"])
        r["llm_judge"] = scores
        for k, v in scores.items():
            if v is not None:
                sums[k].append(v)
        if i % 20 == 0:
            print(f"  ⏳ [{i}/{len(valid)}]")

    avg = {k: (sum(v) / len(v) if v else None) for k, v in sums.items()}
    for k in ("faithfulness", "answer_relevancy", "context_precision", "context_recall"):
        if avg[k] is not None:
            print(f"  ✅ {k:20s}: {avg[k]:.3f}")
        else:
            print(f"  ❌ {k:20s}: 측정 실패")
    return avg


# ─────────────────────────────────────────────────────────
# 단일 질문 평가
# ─────────────────────────────────────────────────────────
def evaluate_one(
    q_item: dict,
    top_k: int = 3,
    prompt_version: str = "v1",
    use_metadata_filter: bool = False,
) -> dict:
    question = q_item["question"]
    expected_kw = q_item.get("expected_keywords", [])
    must_not = q_item.get("must_not_include", [])
    sub_type = q_item.get("sub_type")
    should_have_source = q_item.get("should_have_source", True)
    category = q_item.get("question_type", "single")

    retrieval = measure_retrieval(question, expected_kw, k=top_k)

    start = time.time()
    try:
        result, contexts = answer_with_context(
            question,
            k=top_k,
            prompt_version=prompt_version,
            use_metadata_filter=use_metadata_filter,
        )
        elapsed = time.time() - start

        if expected_kw:
            hit = sum(1 for kw in expected_kw if kw in result)
            accuracy = hit / len(expected_kw)
        else:
            accuracy = 1.0
        if any(kw in result for kw in must_not):
            accuracy = 0.0

        should_be_no_answer = sub_type in ("overseas", "out_of_topic")
        is_no_answer = ("정보가 없" in result) or ("정보 없" in result) or ("찾지 못" in result)
        no_answer_correct = (should_be_no_answer == is_no_answer)

        has_source = "[출처:" in result or "출처:" in result
        citation_correct = (has_source == should_have_source)

        return {
            "id": q_item["id"], "question": question, "answer": result, "contexts": contexts,
            "ground_truth": ", ".join(expected_kw) if expected_kw else "",
            "category": category, "sub_type": sub_type,
            "elapsed": elapsed, "length": len(result), "accuracy": accuracy,
            "no_answer_correct": no_answer_correct, "citation_correct": citation_correct,
            "retrieval": retrieval, "error": None,
        }
    except Exception as e:
        return {
            "id": q_item["id"], "question": question, "answer": "", "contexts": [],
            "ground_truth": "", "category": category, "sub_type": sub_type,
            "elapsed": time.time() - start, "length": 0, "accuracy": 0.0,
            "no_answer_correct": False, "citation_correct": False,
            "retrieval": retrieval, "error": str(e),
        }


# ─────────────────────────────────────────────────────────
# 집계
# ─────────────────────────────────────────────────────────
def aggregate(results: list) -> dict:
    total = len(results)
    if total == 0:
        return {}

    elapsed_sorted = sorted(r["elapsed"] for r in results)
    p95_idx = min(int(total * 0.95), total - 1)

    agg = {
        "accuracy": sum(r["accuracy"] for r in results) / total,
        "citation_accuracy": sum(1 for r in results if r["citation_correct"]) / total,
        "avg_elapsed": sum(r["elapsed"] for r in results) / total,
        "p95_elapsed": elapsed_sorted[p95_idx],
        "avg_length": sum(r["length"] for r in results) / total,
        "error_count": sum(1 for r in results if r["error"]),
    }

    no_ans = [r for r in results if r["sub_type"] in ("overseas", "out_of_topic")]
    agg["no_answer_accuracy"] = sum(1 for r in no_ans if r["no_answer_correct"]) / len(no_ans) if no_ans else None

    by_cat = {}
    for cat in ("single", "compare", "filter", "none"):
        items = [r for r in results if r["category"] == cat]
        if items:
            by_cat[cat] = round(sum(r["accuracy"] for r in items) / len(items), 3)
    agg["by_category"] = by_cat

    by_sub = {}
    for sub in ("overseas", "out_of_topic", "out_of_data"):
        items = [r for r in results if r["sub_type"] == sub]
        if items:
            by_sub[sub] = round(sum(r["accuracy"] for r in items) / len(items), 3)
    agg["by_sub_type"] = by_sub

    retr_cases = [r for r in results if r.get("retrieval") and r["retrieval"]["recall_at_k"] is not None]
    if retr_cases:
        agg["recall_at_k"] = sum(r["retrieval"]["recall_at_k"] for r in retr_cases) / len(retr_cases)
        agg["mrr"] = sum(r["retrieval"]["rr"] for r in retr_cases) / len(retr_cases)
    else:
        agg["recall_at_k"] = None
        agg["mrr"] = None

    return agg


# ─────────────────────────────────────────────────────────
# runs.csv 한 줄 추가
# ─────────────────────────────────────────────────────────
def append_to_runs_csv(exp_id, agg, judge_scores, config, note, csv_path):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    def fmt(v, digits=3):
        return round(v, digits) if v is not None else ""

    row = [
        exp_id, timestamp, config["prompt_version"], config["embedding_model"],
        config["llm_model"], config["temperature"], config["chunk_size"],
        config["chunk_overlap"], config["top_k"], config["dataset_version"],
        fmt(agg["accuracy"]),
        fmt(judge_scores.get("faithfulness")) if judge_scores else "",
        fmt(judge_scores.get("answer_relevancy")) if judge_scores else "",
        fmt(judge_scores.get("context_precision")) if judge_scores else "",
        fmt(judge_scores.get("context_recall")) if judge_scores else "",
        fmt(agg.get("recall_at_k")), fmt(agg.get("mrr")),
        "",  # intent_accuracy (Stage 10)
        fmt(agg["no_answer_accuracy"]), fmt(agg["citation_accuracy"]),
        round(agg["avg_elapsed"], 2), round(agg["p95_elapsed"], 2),
        round(agg["avg_length"]), "",  # cost_per_call_usd
        note,
    ]

    with open(csv_path, "a", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow(row)


# ─────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exp-id", default=None)
    parser.add_argument("--note", default="")
    parser.add_argument("--llm-judge", action="store_true", help="LLM-as-judge 평가 추가 (4지표)")
    parser.add_argument("--top-k", type=int, default=3, help="검색 chunk 수 (기본 3)")
    parser.add_argument("--prompt-version", default="v1", choices=["v1", "v2"], help="시스템 프롬프트 버전")
    parser.add_argument("--metadata-filter", action="store_true", help="룰베이스 메타 필터 적용 (Exp-104)")
    parser.add_argument("--sample", type=int, default=None, help="N문항만")
    args = parser.parse_args()

    config = dict(DEFAULT_CONFIG)
    config["top_k"] = args.top_k
    config["prompt_version"] = args.prompt_version

    exp_id = args.exp_id or f"Exp-{datetime.now().strftime('%y%m%d-%H%M')}"

    base = Path(__file__).parent
    testset_path = base / "testset.json"
    runs_csv_path = base / "runs.csv"
    results_dir = base / "results"
    results_dir.mkdir(exist_ok=True)

    print(f"📂 testset 로드: {testset_path}")
    with open(testset_path, "r", encoding="utf-8") as f:
        testset = json.load(f)
    if args.sample:
        testset = testset[:args.sample]
    print(f"  → {len(testset)}문항")

    print(f"\n🚀 평가 시작 (실험 ID: {exp_id})")
    print(f"   모델: {config['llm_model']} / chunk {config['chunk_size']} / top_k {args.top_k}")
    print(f"   프롬프트: {args.prompt_version} / LLM-as-judge: {'ON' if args.llm_judge else 'OFF'} / MetaFilter: {'ON' if args.metadata_filter else 'OFF'}")
    print("=" * 70)

    results = []
    for i, q in enumerate(testset, 1):
        r = evaluate_one(
            q,
            top_k=args.top_k,
            prompt_version=args.prompt_version,
            use_metadata_filter=args.metadata_filter,
        )
        results.append(r)
        symbol = "✅" if r["accuracy"] >= 0.5 else "❌"
        print(f"  [{i:3d}/{len(testset)}] {symbol} {r['id']} acc={r['accuracy']:.2f} {r['elapsed']:.1f}s | {q['question'][:30]}")

    print("\n" + "=" * 70)
    agg = aggregate(results)
    print(f"\n📊 기본 측정")
    print(f"  정확도:         {agg['accuracy']:.1%}")
    print(f"  출처 포함률:    {agg['citation_accuracy']:.1%}")
    if agg["no_answer_accuracy"] is not None:
        print(f"  no-answer:      {agg['no_answer_accuracy']:.1%}")
    print(f"  평균 응답시간:  {agg['avg_elapsed']:.2f}초 / p95 {agg['p95_elapsed']:.2f}초")
    print(f"  평균 답변길이:  {agg['avg_length']:.0f}자")
    print(f"  에러:           {agg['error_count']}건")

    if agg.get("recall_at_k") is not None:
        print(f"\n🔍 검색 품질 (Stage 6)")
        print(f"  Recall@{args.top_k}: {agg['recall_at_k']:.1%}  /  MRR: {agg['mrr']:.3f}")

    print(f"\n📋 카테고리별 정확도")
    for cat, score in agg["by_category"].items():
        print(f"  {cat:10s}: {score:.1%}")

    if agg["by_sub_type"]:
        print(f"\n📌 sub_type별 정확도")
        for sub, score in agg["by_sub_type"].items():
            print(f"  {sub:14s}: {score:.1%}")

    # LLM-as-judge (옵션)
    judge_scores = None
    if args.llm_judge:
        judge_scores = run_llm_judge(results)

    # runs.csv
    append_to_runs_csv(exp_id, agg, judge_scores, config, args.note, runs_csv_path)
    print(f"\n💾 runs.csv 추가: {exp_id}")

    # 상세 결과
    result_path = results_dir / f"{exp_id}.json"
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump({
            "exp_id": exp_id, "timestamp": datetime.now().isoformat(),
            "config": config, "note": args.note,
            "aggregate": agg, "llm_judge": judge_scores,
            "details": results,
        }, f, ensure_ascii=False, indent=2)
    print(f"💾 상세 결과: {result_path}")
    print("\n✨ 평가 완료\n")


if __name__ == "__main__":
    main()
