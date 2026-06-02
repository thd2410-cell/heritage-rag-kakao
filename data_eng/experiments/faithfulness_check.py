"""faithfulness_check.py — Step 3 미니검증 B: facet 답변이 환각 없이 충실한가.

각 유산: facet 답변 + 전체본문 답변 생성 → 둘 다 '원본 설명문' 대비 Faithfulness 채점.
환각=원본에 없는 사실 지어냄. facet(좁은 근거) vs 전체본문 어느 쪽이 충실한지 비교.

실행: python experiments/faithfulness_check.py
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


def clean(t):
    if not t:
        return ""
    t = re.sub(r"<[^>]+>", "", re.sub(r"<br\s*/?>", " ", t, flags=re.I))
    return re.sub(r"\s+", " ", _CJK.sub("", t)).strip()


def gen(client, name, label, ctx):
    # 강화: 근거 적으면 짧게, 추측·창작 절대 금지 (환각 방지)
    p = (f"너는 국가유산 해설사다. 아래 [근거]에 '실제로 있는 내용만'으로 '{label}' 관심사에 맞춰 "
         f"친근하게 설명해라.\n"
         f"규칙: 근거에 없는 사실은 절대 추측·창작하지 마라. 근거가 적으면 1~2문장으로 짧게 답하고, "
         f"억지로 늘리지 마라. 최대 3문장.\n[유산] {name}\n[근거]\n{ctx}")
    return client.models.generate_content(model="gemini-2.5-flash", contents=p).text.strip()


def judge(client, source, answer):
    p = (f"아래 [원본]에 비추어 [답변]의 Faithfulness(충실성)를 0.0~1.0으로 채점해라.\n"
         f"원본에 없는 사실을 지어냈으면 감점. JSON만: {{\"faithfulness\": 0.0}}\n"
         f"[원본]\n{source}\n[답변]\n{answer}")
    r = client.models.generate_content(model="gemini-2.5-flash", contents=p,
                                       config={"response_mime_type": "application/json"})
    return float(json.loads(r.text).get("faithfulness", 0))


def main():
    facets_data = json.load(open(BASE / "experiments" / "facets_sample.json", encoding="utf-8"))
    heritages = {h["name"]: h for h in json.load(open(BASE / "data" / "heritages.json", encoding="utf-8"))}
    client = genai.Client()

    facet_scores, full_scores = [], []
    for r in facets_data:
        name, facets = r["name"], r.get("facets", {})
        if not isinstance(facets, dict):
            continue
        # 근거 가장 많은 facet 선택
        prim = max((k for k in FLABEL if facets.get(k)), key=lambda k: len(facets[k]), default=None)
        if not prim:
            continue
        source = clean(heritages.get(name, {}).get("description"))[:2000]
        label = FLABEL[prim]

        a_facet = gen(client, name, label, "\n".join(facets[prim]))
        a_full = gen(client, name, label, source)
        f_facet = judge(client, source, a_facet)
        f_full = judge(client, source, a_full)
        facet_scores.append(f_facet)
        full_scores.append(f_full)
        print(f"  {name:12s} [{label}]  facet {f_facet:.2f} / 전체본문 {f_full:.2f}")
        time.sleep(0.4)

    def avg(xs):
        return sum(xs) / len(xs) if xs else 0.0

    print("\n" + "=" * 50)
    print(f"Faithfulness (원본 대비, {len(facet_scores)}개)")
    print(f"  facet 답변:    {avg(facet_scores):.3f}")
    print(f"  전체본문 답변: {avg(full_scores):.3f}")
    print("=" * 50)


if __name__ == "__main__":
    main()
