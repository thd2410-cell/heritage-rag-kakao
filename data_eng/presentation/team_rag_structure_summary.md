# 팀 프로덕션 RAG 구조 — 요약 (재구성본)

> ⚠️ **원본 주의**: 팀원 문서 `CURRENT_RAG_STRUCTURE.md`를 붙여넣기로 받았으나 **한글이 인코딩 깨진 상태(mojibake)** 였음.
> 아래는 **ASCII로 읽힌 부분(숫자·파일경로·코드·구조)을 기준으로 BK/Claude가 재구성한 요약**이다.
> 한글 prose 디테일은 원본 .md를 받아 대조할 것. (이 폴더 README 참조)
> 재구성: 2026-05-31

---

## 1. 서비스 구조

```
사용자
 ├ 웹 챗: https://heritage-chat.com
 └ 카카오 챗봇: /api/kakao/skill
        ↓ Cloudflare Tunnel
React/Vite + nginx (heritage-rag-frontend-prod, 127.0.0.1:3001)  — /api/* → backend proxy
        ↓
FastAPI (heritage-rag-api-prod, 127.0.0.1:8000)
        ↓
PostgreSQL + pgvector (heritage-rag-postgres-prod, 127.0.0.1:5432)
```

## 2. 적재 현황 (★ pitch와 직접 비교)

- 국가유산 **약 17,840건**
- `facet_json`: **전체 생성됨** (status: auto_extracted)
- 좌표: **전체 저장됨**
- `document_chunks`: **약 19,892개**
- 임베딩(bge-m3): **배치 진행 중** (`embedding IS NULL`만 처리, 재시작 가능)

## 3. DB 스키마

- **heritages**: id, name, designation, region, address, latitude, longitude, period, content, raw_json, facet_json
  - ※ `narration_url`(음성) 없음 → pitch 6번 보완 포인트
- **document_chunks**: id, heritage_id, chunk_text, embedding
- **chat_logs**: id, user_key, utterance, answer, sources, created_at (멀티턴 문맥용)

## 4. facet_json 구조 (4종)

`architecture_space` / `story_legend` / `people` / `travel_visit`
- 각 `label` + `evidence:[문장]` + `status`
- `travel_visit`엔 address·lat·long·nearby_heritages·related_events 포함
- ※ 관심사 **4종** (퀴즈 없음) → pitch 7번(5종 고려·확장) 보완 포인트

## 5. 검색 흐름

```
질문 → alias 보정 → 벡터 검색 → 텍스트 fallback → 유산명 fuzzy → 주변유산 attach → answer_builder
```
- `COMMON_NAME_ALIASES`(정남문/남대문→숭례문, 동대문→흥인지문 등) 일부 하드코딩
- 답변: **deterministic / source-grounded builder** (로컬 Qwen 환각 때문에 LLM 자유생성 회피) → 관심사별 분기

## 6. ★ 팀이 자백한 한계 (15절) — pitch_data_eng.md가 1:1 대응

| # | 팀 한계 | pitch 보완 항목 |
|---|---|---|
| 1 | 전체 임베딩 배치 미완료 | (진행 대기) |
| **2** | **벡터 검색 ranking 미검증** | **pitch 1** (정답셋+Recall 리포트) |
| 3 | 오타 보정이 alias/fuzzy 수준 | (한글 자모 fuzzy 후속) |
| 4 | 멀티턴 개선 중 | — |
| **5** | **답변 자연스러움 제한**(deterministic) | **pitch 3** (grounded LLM 제안) |
| **6** | **매칭이 텍스트 기반(공식 관계키 아님)** | **pitch 5** (parent_id 관계키) |
| **7** | **facet_json 자동추출이라 품질 불균일** | **pitch 2** (원인=빈약본문, 충실성 측정·개선) ⭐ |
| 8 | 카카오/웹 답변 로직 미통합 | — |

> + 스키마에 음성 필드 없음 → **pitch 6**(narration_url) / 관심사 4종 → **pitch 7**(5종·확장)

## 7. 주요 파일 (팀 backend)

```
backend/app/api/{rag,kakao}.py
backend/app/services/{retrieval,answer_builder,embedding,guardrails,personalization,text_cleaning,llm}.py
backend/app/models/heritage.py · backend/db/init.sql
frontend/src/App.tsx
scripts/{collect_heritages,build_heritage_json_v1,embed_chunks}.py
docs/{HERITAGE_JSON_V1,RAG_DATA_AND_RECOMMENDATION}.md
```
