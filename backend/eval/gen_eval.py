"""정답지(평가셋) 대량 생성 — LLM 초안 → 사람 검수.

적재된 유산 원문에 근거해 사실형 Q&A 쌍을 LLM이 생성하고, 검수용 초안 JSON으로
저장한다. **반드시 사람이 검토·수정한 뒤** eval_set.json에 합쳐야 한다.

실행 (backend/ 디렉터리에서):
    python eval/gen_eval.py            # 기본 8개 유산, 유산당 2문항
    python eval/gen_eval.py 15 3       # 15개 유산, 유산당 3문항
출력: eval/generated_draft.json
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.llm_api import call_llm  # noqa: E402
from core import vector_store  # noqa: E402

OUT_PATH = Path(__file__).resolve().parent / "generated_draft.json"

_GEN_SYSTEM = """당신은 국가유산 평가 문제 출제자입니다. 아래 [원문]에 근거해 사실 확인용 질문과 정답을 {n}개 만드세요.

규칙:
1. 원문에 근거가 분명한 사실만 출제한다. 원문에 없는 내용은 절대 만들지 않는다.
2. 질문은 관람객이 물을 법한 자연스러운 한 문장으로.
3. 정답은 원문 근거를 담아 1~2문장으로 간결하게.
4. 애매하거나 해석 여지가 큰 것은 피하고, 연도·인물·위치·특징 등 또렷한 사실 위주로.
5. 출력은 **JSON 배열만**. 형식: [{{"q": "질문", "a": "정답"}}]  (다른 말·코드블록 금지)

[유산] {name}
[원문]
{content}"""


def _parse_json_array(text: str) -> list[dict]:
    """LLM 출력에서 JSON 배열을 추출·파싱한다(코드펜스/잡텍스트 방어)."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    m = re.search(r"\[.*\]", text, flags=re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def main(argv: list[str]) -> None:
    n_heritages = int(argv[1]) if len(argv) > 1 else 8
    per = int(argv[2]) if len(argv) > 2 else 2

    names = sorted(vector_store.existing_heritage_names())[:n_heritages]
    print(f"[생성] 유산 {len(names)}개 × 문항 {per}개 (LLM 초안)\n")

    drafts: list[dict] = []
    seq = 1
    for name in names:
        content = "\n".join(vector_store.chunks_of(name))
        if not content:
            continue
        try:
            raw = call_llm(
                _GEN_SYSTEM.format(n=per, name=name, content=content[:1500]),
                "JSON 배열만 출력하세요.",
            )
            pairs = _parse_json_array(raw)
        except Exception as exc:
            print(f"  ! {name}: 생성 실패 ({exc})")
            continue

        for p in pairs:
            q, a = (p.get("q") or "").strip(), (p.get("a") or "").strip()
            if not q or not a:
                continue
            drafts.append(
                {
                    "id": f"gen-{seq:03d}",
                    "category": "생성",
                    "heritage": name,
                    "question": q,
                    "expect": {"type": "judge", "gold": a},
                    "review": True,  # ← 사람 검수 필요 표시
                }
            )
            seq += 1
        print(f"  + {name}: {len(pairs)}문항")
        time.sleep(0.4)

    OUT_PATH.write_text(
        json.dumps(drafts, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n[완료] {len(drafts)}문항 초안 저장 → {OUT_PATH}")
    print("※ 반드시 사람이 검토·수정한 뒤 eval_set.json 에 합치세요. (review 플래그 제거)")


if __name__ == "__main__":
    main(sys.argv)
