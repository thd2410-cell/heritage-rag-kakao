"""faithfulness_3interest.py — facet 충실성을 3개 관심사 전체로 넓혀 측정 (pitch A-1 강화).

기존 0.933은 건축 위주 15건. 이야기·인물 facet도 최종 프롬프트(answer_final)로 답변→채점.
→ 관심사별 + 전체 충실성. 헤드라인 숫자를 단단하게.

실행: python experiments/faithfulness_3interest.py
"""
import json
import re
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai

BASE = Path(__file__).parent.parent
load_dotenv(BASE / "code" / ".env")
_CJK = re.compile(r"[㐀-䶿一-鿿぀-ヿ]+")
FLABEL = {"architecture_space": "건축/공간", "story_legend": "이야기/전설", "people": "인물"}

FINAL_PROMPT = """너는 국가유산 해설사다. 아래 [근거]에 '실제로 있는 내용만'으로 '{label}' 관심사에 맞춰 친근하고 자연스럽게 설명해라.
규칙: 근거에 없는 사실은 절대 추측·창작 금지. 근거 적으면 1~2문장으로 짧게. '근거1' 같은 출처 번호·메타 표현 금지. 최대 3문장.
[유산] {name}
[근거]
{ctx}"""


def clean(t):
    if not t:
        return ""
    t = re.sub(r"<[^>]+>", "", re.sub(r"<br\s*/?>", " ", t, flags=re.I))
    return re.sub(r"\s+", " ", re.sub(r"\(\s*\)", "", _CJK.sub("", t))).strip()


def main():
    facets_data = json.load(open(BASE / "experiments" / "facets_sample.json", encoding="utf-8"))
    heritages = {h["name"]: h for h in json.load(open(BASE / "data" / "heritages.json", encoding="utf-8"))}
    client = genai.Client()

    def gen(name, label, ctx):
        return client.models.generate_content(
            model="gemini-2.5-flash",
            contents=FINAL_PROMPT.format(label=label, name=name, ctx=ctx)).text.strip()

    def judge(source, answer):
        p = (f"[원본]에 비추어 [답변]의 Faithfulness를 0.0~1.0으로 채점(원본에 없는 사실 지어내면 감점). "
             f'JSON만: {{"faithfulness": 0.0}}\n[원본]\n{source}\n[답변]\n{answer}')
        r = client.models.generate_content(model="gemini-2.5-flash", contents=p,
                                           config={"response_mime_type": "application/json"})
        return float(json.loads(r.text).get("faithfulness", 0))

    by_interest = {k: [] for k in FLABEL}
    for r in facets_data:
        name, facets = r["name"], r.get("facets", {})
        if not isinstance(facets, dict):
            continue
        source = clean(heritages.get(name, {}).get("description"))[:2000]
        for fkey, flabel in FLABEL.items():
            ev = facets.get(fkey, [])
            if not ev:
                continue
            ans = gen(name, flabel, "\n".join(ev))
            by_interest[fkey].append(judge(source, ans))
            time.sleep(0.3)

    def avg(xs):
        return sum(xs) / len(xs) if xs else 0.0

    allv = [v for vs in by_interest.values() for v in vs]
    print("\n" + "=" * 50)
    print(f"facet 충실성 — 3개 관심사 전체 (최종 프롬프트, {len(allv)}건)")
    print("=" * 50)
    for k, label in FLABEL.items():
        vs = by_interest[k]
        print(f"  {label:10s}: {avg(vs):.3f}  (n={len(vs)})")
    print(f"  {'전체':10s}: {avg(allv):.3f}  (n={len(allv)})   [건축 위주 15건일 때 0.933]")
    print("=" * 50)


if __name__ == "__main__":
    main()
