# 박스 03 — 임베딩·인덱싱·검증

## 목적
정제된 데이터를 벡터로 임베딩 → 벡터 DB에 인덱싱 → 답변 품질을 정량 검증한다.

## 현재 상태
✅ 1라운드 완료 (통제 실험 4회) — 다음 라운드는 박스 05 결정 이후

## 산출물

- 벡터 DB: `practice/chroma_db/` (627개 인덱싱, KoSimCSE-roberta)
- 인덱서: `practice/rag/indexer.py`
- 검색기: `practice/rag/retriever.py` (질문 → top-k → gpt-4o-mini)
- 평가 도구: `practice/experiments/evaluate.py` (LLM-as-judge)
- 테스트셋: `practice/experiments/testset.json` (80문항)
- 실험 누적: `practice/experiments/runs.csv`, `results/Exp-XXX.json`
- 팀 공유 보고서: `../report/team_report.md`

## 입력 → 출력

```
heritages.json (정제 후)
  ↓ indexer.py (KoSimCSE 임베딩)
ChromaDB
  ↓ retriever.py (top-k 검색 + LLM 답변)
답변 + 출처
  ↓ evaluate.py (Gemini 2.5 Flash 채점)
정확도 / Faithfulness / Recall@K / MRR
```

## 실험 결과 요약 (Exp-100d ~ 104)

| Exp | 변수 | 정확도 | Faithfulness | 결론 |
|---|---|---|---|---|
| 100d | 베이스라인 (k=3, v1) | 66.5% | 0.663 | 기준선 |
| **102** | **Top-K 3→5** | **70.6%** | **0.699** | ✅ **최적** |
| 103 | 프롬프트 v2 (환각 강화) | 50.8% | 0.463 | ⚠️ 역효과 (-19.8%p) |
| 104 | Metadata Filter (룰베이스) | 64.8% | 0.659 | ⚠️ 카테고리 -12%p |

## 현재 최적 설정

```
top_k = 5
prompt_version = v1
metadata_filter = OFF
embedding = KoSimCSE-roberta (정규화 X, 본선에서 ON 예정)
no_answer_threshold = 비활성 (Exp-205a 이후 활성화)
```

## BK 결정 — 잠정

| 항목 | 잠정 | 본선 결정 시점 |
|---|---|---|
| 임베딩 모델 | KoSimCSE (실험), bge-m3 (운영) | 박스 05에서 |
| 벡터 DB | ChromaDB (실험), pgvector (운영) | 박스 05에서 |
| 평가 LLM | Gemini 2.5 Flash 무료 | ✅ 확정 |
| 답변 LLM | gpt-4o-mini | ✅ 확정 |

## 다음 액션

```
🔄 Exp-205a 임베딩 정규화 (발견 003 검증) — 재인덱싱 6h
🔄 Exp-204  LLM 기반 메타 추출 (발견 005 후속)
⬜ Stage 6 검색 품질 (Recall@K, MRR) 자동화
⬜ 시도 종목 추가 후 재인덱싱
⬜ bge-m3 1라운드 평가 (KoSimCSE 결과와 비교)  ← 박스 05 연결
```

## 미해결

- 재인덱싱 6시간이 본선 일정에 맞는지 (Sprint 1 안에 가능?)
- bge-m3 결과가 KoSimCSE보다 나쁘면 어떻게 할지 (운영=KoSimCSE 가능?)

## 참고
- 실험 인사이트·30회 분화: [../experiments.md](../experiments.md)
- 팀 공유 보고서: [../report/team_report.md](../report/team_report.md)
- 검색 발견 003·005: [../feedback_summary.md](../feedback_summary.md)
