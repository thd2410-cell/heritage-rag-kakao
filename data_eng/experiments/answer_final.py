"""answer_final.py — 최종 답변 함수 (발견 005·007 반영) + 엔드투엔드 재확인.

반영한 수정:
  - 엄격 grounding(추측·창작 금지) + 근거 적으면 짧게  ... 발견 005 (환각 0.757→0.933)
  - '근거1' 같은 인용 번호/메타 표현 금지            ... 발견 007 (통합 버그)
  - thin-evidence 가드: 근거 너무 얇으면 전체본문 fallback ... 발견 005 꼬리(동십자각)

실행: python experiments/answer_final.py
"""
import json
import re
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from google import genai
from sentence_transformers import SentenceTransformer

BASE = Path(__file__).parent.parent
load_dotenv(BASE / "code" / ".env")
_CJK = re.compile(r"[㐀-䶿一-鿿぀-ヿ]+")
FLABEL = {"architecture_space": "건축/공간", "story_legend": "이야기/전설", "people": "인물"}
THIN = 50  # 근거 총 글자 < THIN → 전체본문 fallback

FINAL_PROMPT = """너는 국가유산 해설사다. 아래 [근거]에 '실제로 있는 내용만'으로 '{label}' 관심사에 맞춰 친근하고 자연스럽게 설명해라.
규칙:
- 근거에 없는 사실은 절대 추측·창작하지 마라.
- 근거가 적으면 억지로 늘리지 말고 1~2문장으로 짧게.
- '근거1', '(근거2)' 같은 출처 번호나 메타 표현을 절대 쓰지 마라. 자연스러운 해설문만 써라.
- 최대 3문장.
[유산] {name}
[근거]
{ctx}"""


def clean(t):
    if not t:
        return ""
    t = re.sub(r"<[^>]+>", "", re.sub(r"<br\s*/?>", " ", t, flags=re.I))
    t = re.sub(r"\(\s*\)", "", _CJK.sub("", t))     # 한자 제거 + 빈 괄호 제거(발견 006)
    return re.sub(r"\s+", " ", t).strip()


def make_answer(client, name, fkey, facets, full_content):
    """최종 답변. thin-evidence면 전체본문 fallback."""
    ev = facets.get(fkey, [])
    ev_text = "\n".join(ev)
    used = "facet"
    if len(ev_text.replace(" ", "")) < THIN:        # thin 가드
        ev_text = full_content
        used = "fallback(전체본문)"
    r = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=FINAL_PROMPT.format(label=FLABEL[fkey], name=name, ctx=ev_text))
    return used, r.text.strip()


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
    heritages = {h["name"]: h for h in json.load(open(BASE / "data" / "heritages.json", encoding="utf-8"))}
    model = SentenceTransformer("BAAI/bge-m3")
    client = genai.Client()

    def retrieve_top(q):
        qv = model.encode([q], normalize_embeddings=True)[0].astype(np.float32)
        return names[np.argmax(doc_emb @ qv)]

    demo = [
        ("원각사지 십층석탑 건축 설명해줘", "architecture_space"),  # (근거1) 버그 났던 것
        ("숭례문 건축 알려줘", "architecture_space"),
        ("동십자각 건축 알려줘", "architecture_space"),            # thin 가드 테스트
    ]
    for q, fkey in demo:
        print("\n" + "=" * 64)
        print(f"❓ {q}  ({FLABEL[fkey]})")
        top = retrieve_top(q)
        fac = facets.get(top) or next((v for k, v in facets.items() if k in top or top in k), None)
        print(f"🔍 검색: {top}")
        if not fac:
            print("  ⚠️ facet 없음"); continue
        full = clean(heritages.get(top, {}).get("description"))[:2000]
        used, ans = make_answer(client, top, fkey, fac, full)
        print(f"📑 근거: {used}")
        print(f"💬 {ans}")


if __name__ == "__main__":
    main()
