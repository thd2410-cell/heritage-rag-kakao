# 작업 로드맵 v2 — 빌드 먼저, 실험은 그 다음

> 옛 "30 분화 실험 계획"(검색 파라미터 튜닝)을 **현재 상황에 맞게 갈아끼운** 버전.
> 2026-05-31 작성. 관련: [insights_bgem3.md](insights_bgem3.md), [02_refine.md](../02_refine.md) 박스02.5

---

## 왜 v2? (옛 30개가 안 맞는 이유)

1. **검색은 이미 졸업** — bge-m3 single Recall ~100% ([발견 004]). 옛 30개 대부분(chunk/top-k/distance)은 **무의미·해결됨 → 스킵.**
2. **무대가 옮겨감** — 품질은 이제 **답변 생성 / facet / 정제**에서 결정. 그런데 이 단계들이 **아직 안 지어짐.**
3. → **안 지은 걸 튜닝할 순 없다.** 그래서 "어디서 나누지?"가 헷갈림. 답: **지금은 빌드 모드.**

---

## 핵심 사고틀: 모든 단계 = "빌드 → 실험" 2박자

```
① 빌드(make it exist)   : 단계를 일단 존재하게 만든다       ← 지금 대부분 여기
② 실험(tune it)         : 만든 걸 1변수씩 바꿔 비교한다      ← 빌드 끝나야 시작
```
- 옛 "30 분화"는 ②(실험)인데, 지금은 ①(빌드)이 많아서 감이 안 잡힌 것.
- "1변수씩 측정" **규율은 그대로 유지**, 대상만 검색→답변/facet으로 이동.

---

## 단계별 현황 (한눈에)

| 단계 | 상태 | ① 빌드 할 일 | ② 실험(분화) 할 일 | 측정 지표 |
|---|---|---|---|---|
| 수집 | ✅ 10351 | (travel용 좌표·행사만 추가) | — | — |
| 정제 | ✅ 결정됨 | cleaner 분리(선택) | — | — |
| **평가 지표** | ❌ 결함 | **expected_heritage 라벨 + 매칭 고침** | — (인프라) | — |
| 검색 | ✅ ~100% | **완료** | **스킵** ← 옛 30개 여기 | Recall@3 |
| **facet 생성** | ⬜ 미빌드 | **LLM 배치로 facet_json** | 프롬프트, evidence 개수, 룰vsLLM | (facet 품질) |
| **답변 생성** | ⬜ 미빌드 | **facet→LLM 답변 연결** | 프롬프트, facet on/off, 모델, 온도 | Faithfulness, Answer Relevancy |
| 적재 | ⬜ | (docker) load_from_json | — | — |

---

## 크리티컬 패스 (이 순서로 — 의존성 있음)

```
[1] 평가 지표 고치기        ← 블로커. 없으면 그 무엇도 측정 불가
       ↓
[2] facet 생성 빌드        ← 답변의 "재료"
       ↓
[3] 답변 생성 빌드 + 품질 측정 시작
       ↓
[4] 분화 실험 (← 여기서 "30개 정신" 부활, 단 답변/facet 축으로)
```

병렬 가능(크리티컬 패스 밖): travel용 좌표 수집, docker pgvector 적재.

---

## 지금부터 할 일 — 구체 체크리스트

### Step 1. 평가 지표 고치기 ⭐ 1순위 (블로커)
- [ ] testset.json에 `expected_heritage` 정답 필드 추가
  - single: 질문에서 유산명 자동 추출 (예: "경복궁 쉽게 설명" → 경복궁)
  - compare: 유산 2개
  - filter: era/region/category 조건 (유산 1개 아님 → 별도 매칭)
  - none: 빈값
- [ ] 매칭 robustness: 별칭(석가탑=삼층석탑), 띄어쓰기(수원화성=수원 화성) 정규화
- [ ] validate/measure 스크립트가 새 필드 쓰게 수정 → 진짜 Recall 재측정
- **끝나면**: 모든 단계가 측정 가능해짐.

### Step 2. facet 생성 빌드 (1단계: 텍스트 facet)
- [ ] enrich 스크립트: 각 유산 content → LLM(gemini 무료/gpt-4o-mini)에 프롬프트
  - "architecture_space / story_legend / people 에 해당하는 문장을 각각 골라줘"
  - → `facet_json` 생성 (10351개 1회 배치)
- [ ] travel_visit은 좌표 수집 후 2단계 (지금 스킵)
- **끝나면**: 답변에 쓸 facet 재료 확보.

### Step 3. 답변 생성 빌드 + 품질 측정
- [ ] 관심사 선택 → 해당 facet evidence + LLM framing → 답변
  - (백엔드 llm.py 경로 or 자체 retriever)
- [ ] 답변 품질 측정 시작: Faithfulness, Answer Relevancy (BK 보유 LLM-judge)
- **끝나면**: "검색은 됐는데 답변이 좋나?"를 처음으로 측정.

### Step 4. 분화 실험 (빌드 끝난 단계부터)
- facet: 프롬프트 v1/v2, evidence 2개vs4개, 룰vsLLM
- 답변: 프롬프트 버전, facet on/off, gpt-4o-mini vs gpt-4o, 온도
- **고레버리지 5~6개**부터 (30 강박 X)

---

## 옛 30개 → 새 축 매핑 (연속성)

| | 옛 (검색) | 새 (답변/facet) |
|---|---|---|
| 분화 축 | chunk, top-k, overlap, distance | facet 프롬프트, 답변 프롬프트, facet on/off, 모델, 온도 |
| 측정 지표 | Recall@3, MRR | Faithfulness, Answer Relevancy |
| 상태 | 졸업/무의미 | **여기가 진짜 일감** |

→ 방법론(1변수·고정 testset·측정·반복)은 그대로. 무대만 이동.

---

## "지금 할 것" vs "나중"

```
지금 (크리티컬 패스):
  1. 평가 지표 고치기
  2. facet 생성 1단계
  3. 답변 생성 + 품질 측정

나중 (병렬·후순위):
  - travel 좌표·행사 수집 (facet 2단계용)
  - docker + pgvector 적재 (운영 배포)
  - 서버 담당자에게 backend_coordination.md 전달
  - 10351 재임베딩 (캐시 갱신)
```

---

## 한 줄 요약
> **"30개를 어떻게 나누지"가 아니라, "지금은 빌드 단계가 많다 → 빌드부터(평가지표→facet→답변), 분화 실험은 그 다음."**
> 검색은 졸업했고, 무대는 답변/facet으로 옮겨갔다.
