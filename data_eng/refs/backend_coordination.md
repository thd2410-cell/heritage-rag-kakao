# 백엔드 협의 — 데이터 적재 / 한자 / 관심사 framing

> 보내는 사람: BK (데이터 엔지니어링 파트)
> 작성: 2026-05-31
> 대상: 백엔드 담당자
> 목적: 데이터 적재 방식·스키마·답변 framing 3건 합의

---

## 1. 데이터 적재 — 전 종목 ~15K를 pgvector로

**상황**
- 내가 국가유산검색 API로 전 종목(국가+시도) ~15,000개를 수집해 `heritages.json`으로 보유(현재 5,743, 수집 진행 중).
- 이걸 백엔드 `heritages` + `document_chunks`(bge-m3, cosine) 스키마로 적재하려 함.

**BK 결정**
- `scripts/load_from_json.py` 신규 작성: json → `heritages` upsert → chunk → bge-m3 임베딩 → `document_chunks`.
- 필드 매핑·정제는 기존 `collect_heritages.py` / `text_cleaning.py` / `chunking.py` **재사용**해서 드리프트 방지.
- 기존 `collect_heritages.py`는 **빠른 개발 시드로 유지**(대체 X). 역할 분담: 시드 vs 본적재.

**백엔드에 묻는 것**
1. **운영 DB(맥미니) 적재는 누가/언제 실행?** (BK가 PR + 스크립트 제공 → 백엔드가 실행하는 그림으로 생각 중)
2. `scripts/load_from_json.py` 추가 OK? 기존 `collect_heritages.py`와 **공존** 방향 동의?

---

## 2. 한자 처리 — `name_hanja` 별도 필드 확장 요청

**상황**
- 현재 백엔드는 한자를 **제거**(`text_cleaning.remove_unwanted_cjk`, llm 프롬프트도 "한자 최소 허용").
- 내 정제 결정(④)은 **C안: 한글 `name` / 한자 `name_hanja` 분리** (외국인·다국어 P1 검색 대비).

**BK 결정 (지금)**
- 당장은 **백엔드 방식(한자 제거, A안)으로 적재**해서 검증 막힘 없이 진행.
- 단, **C안(name_hanja 분리)을 목표로 두고 확장 요청.**

**백엔드에 묻는 것**
3. extra 필드(name_hanja·parent_id·designation_date 등)는 우선 **`raw_json`(JSONB)** 에 보존하려 함. OK?
4. 나중에 `name_hanja`가 실제 검색에 쓰이면 **정식 컬럼으로 승격**(init.sql 변경) 협의 가능한지?
   - ※ 이 경우 fetcher가 한자명(ccbaMnm2)도 뽑도록 내가 수정 필요 — 그건 내 쪽 작업.

---

## 3. 관심사 답변 — `answer_builder` 키워드 → 기존 `llm.py` framing 경로로

**상황**
- `/api/rag/ask`는 현재 `answer_builder.py`의 **하드코딩 KEYWORDS**로 관심사별 문장을 추출.
  - 예: `people=[진흥왕, 김정희]`, `travel=[비봉, 경복궁]` → **현재 20개 데이터(진흥왕 순수비)에 과적합.**
  - 15K로 가면 엔티티마다 키워드 하드코딩 불가 → **스케일 안 됨.**
- 한편 `llm.py`에 **이미 LLM framing이 구현됨**(`build_audience_instruction`: 관심사를 말투·강조점·후속질문에만 반영) — 단 `/ask`에 연결 안 됨.

**BK 제안**
- `/ask`를 **answer_builder(키워드) → llm.py framing 경로로 전환** 제안.
- 데이터엔지 입장: **데이터를 키워드 분류기에 맞게 정제(왜곡)하는 방향은 반대.** 데이터는 출처에 충실하게 두고, 관심사는 **표현(framing)** 에서 LLM으로 처리하는 게 15K에 맞음.
- 키워드 vs LLM 답변 차이를 **로컬에서 시연**해서 공유하겠음.

**백엔드에 묻는 것**
5. `/ask`를 llm.py 경로로 전환하는 것 어떻게 보는지? (비용·지연·결정성 트레이드오프 포함 논의)
6. 전환 전까지 answer_builder KEYWORDS는 15K 적재 후 **재설계 필요** — 같이 볼지?

---

## 요약 (백엔드 결정 필요한 것)
| # | 항목 | 묻는 것 |
|---|---|---|
| 1 | 적재 | 운영 적재 누가/언제, load_from_json 추가·공존 OK? |
| 2 | 한자 | raw_json 보존 OK? name_hanja 컬럼 승격 협의 가능? |
| 3 | framing | /ask를 llm.py 경로로 전환 어떻게 보는지? |
