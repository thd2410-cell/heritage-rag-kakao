"""facet_generate.py — 유산 content에서 관심사별 evidence를 LLM(gemini)으로 추출 (Step 2, 1단계).

서버 facet_json 구조 채우기. 1단계 = 텍스트 facet 3종(travel_visit은 좌표 수집 후 2단계).
sample-first: 먼저 --limit 소수로 프롬프트 품질 검증 → 좋으면 전체 배치.

실행: python experiments/facet_generate.py --limit 15
"""
import argparse
import json
import re
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai

BASE = Path(__file__).parent.parent
load_dotenv(BASE / "code" / ".env")
_CJK = re.compile(r"[㐀-䶿一-鿿぀-ヿ]+")


def clean(text):
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = _CJK.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


PROMPT = """다음은 한 국가유산의 공식 설명문이다. 관심사별로 관련 '문장'을 설명문에서 골라라.

- architecture_space (건축/공간): 형태, 구조, 양식, 크기, 배치, 공간 관련 문장
- story_legend (이야기/전설): 유래, 사건, 전승, 발견, 일화 관련 문장
- people (인물): 인물, 왕, 제작자, 관련 인물이 등장하는 문장

규칙:
- 반드시 설명문에 '실제로 있는' 문장만 골라라. 새로 짓거나 요약·창작 금지.
- 해당 관심사 내용이 없으면 빈 배열 [].
- 각 facet 최대 3문장.

JSON만 출력(다른 말 금지):
{{"architecture_space": [], "story_legend": [], "people": []}}

[설명문]
{content}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=15)
    ap.add_argument("--idprefix", default=None, help="종목 필터 (예: K11=국보, K12=보물)")
    ap.add_argument("--out", default=str(BASE / "experiments" / "facets_sample.json"))
    args = ap.parse_args()

    heritages = json.load(open(BASE / "data" / "heritages.json", encoding="utf-8"))
    # 본문 충분한 것 위주로 샘플 (+ 종목 필터)
    cands = [h for h in heritages
             if len(clean(h.get("description"))) >= 100
             and (not args.idprefix or str(h.get("id", "")).startswith(args.idprefix))][: args.limit]
    print(f"샘플 {len(cands)}개 (idprefix={args.idprefix})")

    client = genai.Client()
    results = []
    for i, h in enumerate(cands, 1):
        content = clean(h.get("description"))[:2000]
        try:
            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=PROMPT.format(content=content),
                config={"response_mime_type": "application/json"},
            )
            facets = json.loads(resp.text)
        except Exception as e:
            facets = {"error": str(e)[:120]}
        results.append({"id": h.get("id"), "name": h.get("name"), "facets": facets})
        print(f"  [{i}/{len(cands)}] {h.get('name')}")
        time.sleep(0.5)

    json.dump(results, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n저장: {args.out} ({len(results)}개)")
    # 샘플 2개 미리보기
    for r in results[:2]:
        print(f"\n=== {r['name']} ===")
        print(json.dumps(r["facets"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
