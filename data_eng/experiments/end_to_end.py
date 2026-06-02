"""end_to_end.py — 전체 체인 통합 검증: 질문 → 검색 → facet → 관심사 답변.

지금까지 조각별로만 검증함(검색 100% / facet 충실 / 답변 framing).
이 스크립트는 처음으로 합쳐서 돌림 → 통합 갭 확인.

전제: _emb_name.npz 캐시 + facets_sample.json/facets_gukbo.json (facet 보유 유산만).
실행: python experiments/end_to_end.py
"""
import json
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from google import genai
from sentence_transformers import SentenceTransformer

BASE = Path(__file__).parent.parent
load_dotenv(BASE / "code" / ".env")
FLABEL = {"architecture_space": "건축/공간", "story_legend": "이야기/전설", "people": "인물"}

# (질문, 관심사) — facet 보유 유산 대상
DEMO = [
    ("숭례문 건축 알려줘", "architecture_space"),
    ("숭례문은 무슨 이야기가 있어?", "story_legend"),
    ("광화문은 누가 만들었어?", "people"),
    ("원각사지 십층석탑 건축 설명해줘", "architecture_space"),
]


def main():
    d = np.load(BASE / "experiments" / "_emb_name.npz", allow_pickle=True)
    doc_emb, names = d["emb"], d["names"]

    facets = {}
    for fn in ("facets_sample.json", "facets_gukbo.json"):
        p = BASE / "experiments" / fn
        if p.exists():
            for r in json.load(open(p, encoding="utf-8")):
                if isinstance(r.get("facets"), dict):
                    facets[r["name"]] = r["facets"]
    print(f"facet 보유 유산: {len(facets)}개")

    model = SentenceTransformer("BAAI/bge-m3")
    client = genai.Client()

    def retrieve_top(question):
        qv = model.encode([question], normalize_embeddings=True)[0].astype(np.float32)
        sims = doc_emb @ qv
        for i in np.argsort(-sims):
            return names[i]  # top-1 유산

    def answer(name, label, evidence):
        p = (f"너는 국가유산 해설사다. 아래 [근거]에 '실제로 있는 내용만'으로 '{label}' 관심사에 맞춰 "
             f"친근하게 설명해라. 근거에 없는 사실은 추측·창작 금지. 근거 적으면 짧게. 최대 3문장.\n"
             f"[유산] {name}\n[근거]\n{evidence}")
        return client.models.generate_content(model="gemini-2.5-flash", contents=p).text.strip()

    for q, fkey in DEMO:
        print("\n" + "=" * 64)
        print(f"❓ 질문: {q}  (관심사: {FLABEL[fkey]})")
        top = retrieve_top(q)
        print(f"🔍 검색 top-1 유산: {top}")
        # facet 매칭 (정확 or 부분)
        fac = facets.get(top) or next((v for k, v in facets.items() if k in top or top in k), None)
        if not fac:
            print("  ⚠️ 이 유산의 facet 없음 (생성 필요) → 체인 중단")
            continue
        ev = fac.get(fkey, [])
        if not ev:
            print(f"  ⚠️ '{FLABEL[fkey]}' facet 비어있음")
            continue
        print(f"📑 facet evidence {len(ev)}문장 → 답변 생성")
        print(f"💬 답변: {answer(top, FLABEL[fkey], chr(10).join(ev))}")


if __name__ == "__main__":
    main()
