"""facet_answer_demo.py — Step 3 미니 검증: facet→답변 (관심사별 차이 + facet vs 전체본문).

비교:
  ① 같은 유산 + 관심사 3개(건축/이야기/인물) → 답변이 관심사대로 달라지나
  ② facet 방식(해당 evidence만) vs 옛 방식(전체 본문) → facet이 더 집중되나

실행: python experiments/facet_answer_demo.py
"""
import json
import re
from pathlib import Path

from dotenv import load_dotenv
from google import genai

BASE = Path(__file__).parent.parent
load_dotenv(BASE / "code" / ".env")
_CJK = re.compile(r"[㐀-䶿一-鿿぀-ヿ]+")

FACETS = {"architecture_space": "건축/공간", "story_legend": "이야기/전설", "people": "인물"}


def clean(t):
    if not t:
        return ""
    t = re.sub(r"<[^>]+>", "", re.sub(r"<br\s*/?>", " ", t, flags=re.I))
    return re.sub(r"\s+", " ", _CJK.sub("", t)).strip()


def ask(client, name, interest_label, evidence_text):
    prompt = (
        f"너는 국가유산 해설사다. 아래 [근거]만 바탕으로 '{interest_label}' 관심사에 맞춰 "
        f"친근하게 3문장으로 설명해라. 근거에 없는 내용은 만들지 마라.\n"
        f"[유산] {name}\n[근거]\n{evidence_text}"
    )
    r = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    return r.text.strip()


def main():
    facets_data = json.load(open(BASE / "experiments" / "facets_sample.json", encoding="utf-8"))
    heritages = {h["name"]: h for h in json.load(open(BASE / "data" / "heritages.json", encoding="utf-8"))}
    client = genai.Client()

    targets = ["광화문", "건춘문"]
    for r in facets_data:
        if r["name"] not in targets:
            continue
        name, facets = r["name"], r["facets"]
        full = clean(heritages.get(name, {}).get("description"))[:2000]
        print("\n" + "#" * 64)
        print(f"# {name}")
        print("#" * 64)

        # ① 관심사별 facet 답변
        for fkey, flabel in FACETS.items():
            ev = facets.get(fkey, [])
            if not ev:
                continue
            print(f"\n[{flabel}] (facet evidence {len(ev)}문장)")
            print("  →", ask(client, name, flabel, "\n".join(ev)))

        # ② facet vs 전체본문 (건축 관심사로)
        if facets.get("architecture_space"):
            print(f"\n--- 비교(건축 관심사): facet vs 전체본문 ---")
            print("  [facet]    →", ask(client, name, "건축/공간", "\n".join(facets["architecture_space"])))
            print("  [전체본문] →", ask(client, name, "건축/공간", full))


if __name__ == "__main__":
    main()
