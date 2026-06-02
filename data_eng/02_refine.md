# 박스 02 — 정제 (스키마 결정 + Cleaning)

## 목적
원천 데이터를 RAG가 검색·답변하기 좋은 형태로 변환한다.

## 현재 상태
🔄 BK 결정 진행 중 (8개 항목)

> ⚠️ data_schema.md는 원래 "팀원 회신 대기"였지만 BK가 데이터 엔지니어링 담당자이므로
> **이제 결정권은 BK 본인**. "팀원 결정" 칸 → "BK 결정" 칸으로 톤 전환 필요.

## 산출물 (예정)

- 결정된 스키마 문서: [../data_schema.md](../data_schema.md) (BK 결정 채워서)
- 정제 코드: `practice/rag/cleaner.py` (현재는 fetcher 안에 일부 내장 — 분리 필요)
- 정제 결과: `heritages.json` (cleaned)
- 메타 표준화 매핑 사전: `practice/data/meta_mappings.json` (예정)

## 8개 결정 항목 — BK 현재 의견

| # | 항목 | BK 의견 | 근거 |
|---|---|---|---|
| ① | 포함 필드 | name, description, location, era, region, category, image_url, narration_url, source_url | 답변·검색 모두 필요 |
| ② | chunk 단위 | 유산 1개 = chunk 1개 (현 indexer.py 방식) | 설명문 200~500자 평균 |
| ③ | HTML/특수문자 | 전부 제거, 엔티티 디코딩, 공백 정규화 | 검색·답변 노이즈 ↓ |
| ④ | 한자 처리 | C안 — `name`은 한글만, `name_hanja` 별도 필드 | 둘 다 검색 가능 + 답변 자연스러움 |
| ⑤ | 동일 유산 (경복궁 vs 광화문 vs 근정전) | 별도 보존 + `parent_id` 메타 연결 | 각각 검색 가능해야 함 |
| ⑥ | 결측 | description 50자 미만 → 인덱싱 제외 | 검색돼봤자 답변 못 만듦 |
| ⑦ | 출처 표기 | A안 — `[출처: 국가유산포털]` (간결) | URL은 webLink 버튼에서 처리 |
| ⑧ | 메타 표준화 | 매핑 사전 필수 (era/region/category) | Metadata Filtering 동작 조건 |

## BK 결정 — 다음 액션

```
⭐ [../data_schema.md](../data_schema.md) 의 "팀원 결정: (회의 후 채움)" 8칸을
   "BK 결정: ..." 으로 직접 채우기 (이제 결정권자가 BK 본인)

⬜ 메타 표준화 매핑 사전 작성
   - era: "조선 시대"/"조선시대"/"朝鮮" → "조선"
   - region: "서울특별시 종로구"/"서울 종로구" → "서울"
   - category: "궁궐"/"궁"/"왕궁" → "궁궐"

⬜ cleaner.py 분리 (fetcher 안의 정제 로직 떼어내기)
```

## 정제 룰이 답변 품질에 미치는 영향

| 결정 | RAG 평가 영향 |
|---|---|
| 한자 처리 (A/B/C) | Answer Relevancy ±2~5%p |
| 메타 표준화 | Metadata Filtering 정확도 ±10%p |
| 결측치 처리 | Recall@3 ±3%p |
| chunk 단위 | Faithfulness ±3~7%p |
| HTML 정제 | 환각률 ±2%p |

→ 정제 방식이 본선 발표 수치에 직접 영향.

## 박스 02.5 — 라벨링 / facet enrichment (서버 협의 2026-05-31)

> 정제(있는 필드 다듬기) **다음**, 인덱싱 **전**의 데이터 준비 단계. 정제와 이웃이라 박스 02에 포함.
> 정제 ≠ 라벨링: 정제는 "한 번 하면 끝", 라벨은 "파생이라 언제든 재생성".

**서버가 정한 구조**: `heritages` 테이블에 기본정보 + **`facet_json`** 저장.
- facet_json = 유산마다 **관심사별 evidence 문장을 미리 계산**해 저장.
  - `architecture_space` / `story_legend` / `people` / `travel_visit`
  - 각 facet에 `evidence: [관련 문장들]`
- query-time엔 사용자 선택 관심사의 facet evidence를 **골라쓰기만** → 빠름·결정적·per-query LLM 비용 0.
- answer_builder 하드코딩 키워드의 진화형 (offline 미리 추출 → 저장).

**분담**: 서버 = 스키마 + 질의 로직 / **BK = facet_json 생성(LLM enrichment)**.

**🔑 evidence 추출은 LLM 배치로** (BK 도메인):
- 유산 content → LLM "이 facet들에 해당하는 문장 골라줘" → facet_json. 15K 1회 배치(gemini 무료/gpt-4o-mini).
- ⚠️ 키워드로 뽑으면 과적합(answer_builder 전철) → **LLM 필수.**

**단계적 도입**:
```
1단계: 텍스트 facet (architecture/story/people)  ← content만, LLM. 좌표 불필요. 지금 가능
2단계: travel_visit                             ← 좌표(위치API)+거리계산(nearby)+행사API(events). 나중
```

**갭/의존성**:
- travel_visit의 nearby = **좌표(lat/long) 필요** → BK 현재 데이터에 없음(fetcher 미수집) → 위치 API(gis-heritage) 수집 추가.
- related_events = 행사 API 수집 추가 (data_sources.md에 있음).
- facet_json 컬럼 = init.sql 변경 = **서버 소유**(이미 설계함).

## 미해결

- 한자 별도 필드(`name_hanja`) → 팀 PostgreSQL 스키마에 컬럼 추가 필요? 박스 05에서 합의
- 메타 표준화 매핑 사전 누가 만들지 (BK 직접 vs LLM 추출 — 발견 005)
- facet evidence LLM 추출 프롬프트 설계 (1단계 착수 시)

## 참고
- 정제 협의 문서 (BK 결정 문서로 톤 전환 필요): [../data_schema.md](../data_schema.md)
- 메타 추출 LLM 실험 후속: Exp-204 (experiments.md)
