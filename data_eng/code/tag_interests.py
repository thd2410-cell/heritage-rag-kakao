"""
tag_interests.py — heritages.json에 관심사(interest) 태그 부여 (A안 / 보강 레이어)

박스 02.5 보강(Enrichment). 정제(data_schema.md)와 분리된 레이어.
설계·논의 문서: refs/interest_tagging.md

핵심 원칙 (락인 방지 4원칙):
  1. description 원문 불변 — interest_* 별도 필드만 추가 (출처 충실, backend_coordination §3)
  2. Gemini 분류 사용 (규칙 키워드 아님) — 15K 일반화, 과적합 회피
  3. 출처·버전 기록 (interest_meta) — 나중에 B안이 약한 태그만 교체 가능
  4. 재실행 가능(idempotent) — 다시 돌리면 깨끗이 재생성

실행:
  python rag/tag_interests.py --limit 30      # 시범: 30건만 태깅
  python rag/tag_interests.py                 # 전체 (이미 태깅된 건 건너뜀)
  python rag/tag_interests.py --force         # 버전 올려 전체 재태깅
  python rag/tag_interests.py --rethreshold 0.6   # Gemini 재호출 없이 임계값만 재적용
  python rag/tag_interests.py --dry-run --limit 5 # 저장 안 하고 결과만 출력

전제: .env에 GOOGLE_API_KEY (무료 Gemini 2.5 Flash)
"""
import argparse
import json
import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

# ─────────────────────────────────────────────────────────
# 0. 상수 — 관심사 5종은 백엔드 answer_builder.KEYWORDS 키와 정렬
#    (카테고리 확장 논의는 refs/interest_tagging.md §6 참조)
# ─────────────────────────────────────────────────────────
SCHEMA_VERSION = "v1"
DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_THRESHOLD = 0.5

INTERESTS = {
    "architecture": "형태·구조·축조 방식 (기둥·지붕·양식·석축·층 등)",
    "people": "관련 인물·왕·재위 (인물명·장군·왕조 등)",
    "travel": "위치·방문·소장처 (주소·소재지·박물관·관람 정보)",
    "story": "발견·설화·일화 (전설·유래·발견 경위)",
    "quiz": "수치·연대·지정 등 팩트 (크기·연대·국보 호수·지정일)",
}


# ─────────────────────────────────────────────────────────
# 1. 프롬프트 — 5종 점수 + 한 줄 근거를 JSON으로
# ─────────────────────────────────────────────────────────
def build_prompt(item: dict) -> str:
    lines = "\n".join(f"  - {k}: {desc}" for k, desc in INTERESTS.items())
    return (
        "다음 국가유산 설명을 읽고, 5개 관심사 각각에 대해 이 유산이 "
        "얼마나 풍부한 정보를 담는지 0.0~1.0으로 채점하라.\n"
        "유산마다 여러 관심사가 동시에 높을 수 있다 (멀티라벨).\n\n"
        f"관심사:\n{lines}\n\n"
        f"[유산명] {item.get('name','')}\n"
        f"[분류] {item.get('category','')}\n"
        f"[설명] {item.get('description','')[:1500]}\n\n"
        'JSON만 출력: {"scores":{"architecture":0.0,"people":0.0,'
        '"travel":0.0,"story":0.0,"quiz":0.0},"reason":"한 줄 근거"}'
    )


# ─────────────────────────────────────────────────────────
# 2. Gemini 분류 (1건) → {scores, reason}
# ─────────────────────────────────────────────────────────
def classify(client: genai.Client, model: str, item: dict) -> dict | None:
    try:
        resp = client.models.generate_content(
            model=model,
            contents=build_prompt(item),
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
            ),
        )
        data = json.loads(resp.text)
        raw = data.get("scores", {})
        # 5종 전부 보정해서 저장 (누락 키는 0.0, 0~1 클램프)
        scores = {k: max(0.0, min(1.0, float(raw.get(k, 0.0)))) for k in INTERESTS}
        return {"scores": scores, "reason": str(data.get("reason", ""))[:200]}
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️ 분류 실패 ({item.get('id')}): {e}")
        return None


# ─────────────────────────────────────────────────────────
# 3. 점수 → interests 리스트 (임계값 적용). Gemini 재호출 없음.
# ─────────────────────────────────────────────────────────
def derive_interests(scores: dict, threshold: float) -> list:
    return [k for k, v in scores.items() if v >= threshold]


def apply_tags(item: dict, scores: dict, reason: str, threshold: float, tagged_at: str, model: str):
    item["interest_scores"] = scores
    item["interests"] = derive_interests(scores, threshold)
    item["interest_meta"] = {
        "source": model,
        "schema_version": SCHEMA_VERSION,
        "tagged_at": tagged_at,
        "reason": reason,
    }


# ─────────────────────────────────────────────────────────
# 4. 원자적 저장 (중간 실패해도 원본 안 깨짐)
# ─────────────────────────────────────────────────────────
def save_atomic(path: Path, data):
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="N건만 태깅 (시범)")
    ap.add_argument("--force", action="store_true", help="이미 태깅된 것도 재태깅")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD, help="interests 임계값")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--rethreshold", type=float, default=None,
                    help="Gemini 재호출 없이 저장된 점수에 임계값만 재적용")
    ap.add_argument("--dry-run", action="store_true", help="저장 안 하고 결과만 출력")
    args = ap.parse_args()

    base = Path(__file__).parent.parent
    load_dotenv(Path(__file__).parent / ".env")
    data_path = base / "data" / "heritages.json"

    with open(data_path, "r", encoding="utf-8") as f:
        heritages = json.load(f)
    print(f"데이터 {len(heritages)}개 로드됨")

    # ── 모드 A: 임계값만 재적용 (API 호출 0, 공짜) ───────────
    if args.rethreshold is not None:
        n = 0
        for h in heritages:
            if "interest_scores" in h:
                h["interests"] = derive_interests(h["interest_scores"], args.rethreshold)
                n += 1
        print(f"임계값 {args.rethreshold} 재적용: {n}건")
        if not args.dry_run:
            save_atomic(data_path, heritages)
            print("저장 완료")
        return

    # ── 모드 B: Gemini 태깅 ─────────────────────────────────
    # TODO(BK): 시범(--limit 30) 후 30건 스팟체크 → 프롬프트/임계값 조정 → 전체 실행
    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    tagged_at = os.environ.get("TAG_DATE", "2026-05-31")  # Date.now 회피: 고정/주입

    targets = []
    for h in heritages:
        meta = h.get("interest_meta", {})
        already = meta.get("schema_version") == SCHEMA_VERSION
        if already and not args.force:
            continue  # idempotent: 같은 버전이면 건너뜀
        targets.append(h)
    if args.limit:
        targets = targets[: args.limit]

    print(f"태깅 대상 {len(targets)}건 (모델: {args.model}, 임계값: {args.threshold})")
    done = 0
    for i, h in enumerate(targets, 1):
        result = classify(client, args.model, h)
        if result is None:
            continue
        apply_tags(h, result["scores"], result["reason"], args.threshold, tagged_at, args.model)
        done += 1
        if args.dry_run:
            print(f"  [{i}] {h.get('name')}: {h['interests']}  ← {result['reason']}")
        elif i % 50 == 0:
            print(f"  진행 {i}/{len(targets)}")
            save_atomic(data_path, heritages)  # 중간 저장 (긴 작업 보호)

    print(f"태깅 완료: {done}건")
    if not args.dry_run:
        save_atomic(data_path, heritages)
        print(f"저장 완료 → {data_path}")


if __name__ == "__main__":
    main()