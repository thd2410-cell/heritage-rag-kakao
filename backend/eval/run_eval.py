"""정확도 평가 하니스.

정답지(eval_set.json)의 각 질문을 RAG 파이프라인에 넣고, 유형별로 채점해
카테고리별·전체 정확도를 출력한다.

실행 (backend/ 디렉터리에서):
    python eval/run_eval.py
    python eval/run_eval.py --save report.json
"""

from __future__ import annotations

import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

# backend/ 를 import 경로에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.llm_api import call_llm  # noqa: E402
from core.pipeline import rag_answer  # noqa: E402

EVAL_PATH = Path(__file__).resolve().parent / "eval_set.json"

# '거부(확인 불가)' 표현 패턴
_REFUSE_RE = re.compile(
    r"(확인되지\s*않|확인할\s*수\s*없|자료에[^.]{0,12}없|찾을\s*수\s*없|담겨\s*있지\s*않|제공[^.]{0,8}없)"
)

_JUDGE_SYSTEM = """당신은 엄격하고 공정한 채점자입니다. 아래 [질문]에 대한 [정답지]와 [챗봇 답변]을 비교하세요.

판정 기준:
- 챗봇 답변이 정답지의 '핵심 사실'과 일치하고 모순이 없으면 '정답'.
- 핵심이 틀렸거나, 빠졌거나, 정답지와 모순되면 '오답'.
- 문장·표현이 달라도 의미가 맞으면 정답이다. 정답지에 없는 추가 설명이 있어도 핵심만 맞으면 정답.

반드시 첫 단어로 '정답' 또는 '오답'만 쓰고, 그 뒤에 짧은 이유 한 줄을 붙이세요.

[질문]
{q}

[정답지]
{gold}

[챗봇 답변]
{ans}"""


def grade(item: dict, answer: str) -> tuple[bool, str]:
    """채점 → (정답 여부, 사유)."""
    exp = item["expect"]
    t = exp["type"]

    if t == "keywords":
        low = answer.lower()
        for kw in exp.get("must_include", []):
            if kw.lower() not in low:
                return False, f"누락 키워드: '{kw}'"
        for kw in exp.get("must_not_include", []):
            if kw.lower() in low:
                return False, f"금지 키워드 포함: '{kw}'"
        return True, "핵심 키워드 충족"

    if t == "refuse":
        ok = bool(_REFUSE_RE.search(answer))
        return ok, "거부 표현 확인" if ok else "거부했어야 하는데 단정적으로 답함"

    if t == "judge":
        verdict = call_llm(
            _JUDGE_SYSTEM.format(q=item["question"], gold=exp["gold"], ans=answer),
            "정답 또는 오답으로 판정하세요.",
        ).strip()
        ok = verdict.startswith("정답") and not verdict.startswith("정답이 아")
        return ok, verdict[:80]

    return False, f"알 수 없는 채점 유형: {t}"


def main(argv: list[str]) -> None:
    items = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    print(f"[정확도 평가] {len(items)}문항\n" + "=" * 64)

    results = []
    by_cat = defaultdict(lambda: [0, 0])  # category -> [correct, total]
    for it in items:
        try:
            resp = rag_answer(it["question"], lang="ko", top_k=6, history=[], user_id=None)
            ok, reason = grade(it, resp.answer)
        except Exception as exc:  # 호출 실패는 오답 처리
            ok, reason, resp = False, f"오류: {exc}", None
        mark = "✅" if ok else "❌"
        cat = it.get("category", "기타")
        by_cat[cat][1] += 1
        by_cat[cat][0] += int(ok)
        results.append({"id": it["id"], "category": cat, "ok": ok, "reason": reason,
                        "question": it["question"]})
        print(f"{mark} [{cat}] {it['id']}")
        if not ok:
            print(f"     ↳ {reason}")
        time.sleep(0.4)  # 레이트리밋 완화

    correct = sum(r["ok"] for r in results)
    total = len(results)
    print("\n" + "─" * 64 + "\n[카테고리별]")
    for cat, (c, t) in sorted(by_cat.items()):
        print(f"  {cat:<6} {c}/{t}  ({round(100 * c / t)}%)")
    acc = round(100 * correct / total, 1) if total else 0
    print("\n" + "═" * 64)
    print(f"  전체 정확도: {correct}/{total}  ({acc}%)")
    print("═" * 64)

    # --save report.json
    if "--save" in argv:
        out = Path(argv[argv.index("--save") + 1])
        out.write_text(
            json.dumps({"accuracy": acc, "correct": correct, "total": total,
                        "results": results}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n[저장] {out}")


if __name__ == "__main__":
    main(sys.argv)
