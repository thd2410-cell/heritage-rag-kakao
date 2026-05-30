# RAG 원리와 우리 프로젝트 적용

> 이 문서는 **RAG(Retrieval-Augmented Generation, 검색 증강 생성)** 의 원리를 설명하고,
> 그것이 "국가유산 AI 해설사" 프로젝트에 **어떤 파일·함수로 구현되어 있는지** 코드와 함께 매핑한다.

---

## 1. RAG란 무엇인가?

### 문제: LLM 단독의 한계
LLM(Gemini, GPT 등)은 강력하지만 두 가지 약점이 있다.

1. **환각(Hallucination)** — 모르는 것도 그럴듯하게 지어낸다.
2. **지식의 한계/최신성** — 학습 시점 이후 정보나, 특정 도메인의 세부 사실(예: 특정 국가유산의 정확한 연혁)을 모른다.

예를 들어 "숭례문은 폭설로 무너진 적 있어?" 라고 물으면, 학습 데이터에만 의존하는 LLM은
부정확하게 답하거나 잘못된 전제("네, 폭설로...")에 끌려갈 수 있다.

### 해결: RAG
> **"LLM에게 답하게 하기 전에, 신뢰할 수 있는 자료를 먼저 검색해서 근거로 쥐여준다."**

LLM의 추론 능력은 그대로 쓰되, **사실의 출처는 우리가 통제하는 문서(국가유산청 원문)** 로 고정한다.
검색된 자료에 없으면 "확인되지 않습니다"라고 답하게 만들어 **환각을 차단**한다.

---

## 2. RAG의 4단계

RAG는 크게 **사전 준비(Indexing)** 와 **질의 시점(Query time)** 으로 나뉜다.

```
[사전 준비 — 1회]
  문서 ─→ ① 청킹(Chunking) ─→ ② 임베딩(Embedding) ─→ ③ 벡터 DB 저장(Indexing)

[질의 시점 — 매 질문마다]
  질문 ─→ ② 임베딩 ─→ ④ 검색(Retrieval) ─→ ⑤ 컨텍스트 주입(Augmentation) ─→ ⑥ 생성(Generation)
```

| 단계 | 개념 | 한 줄 설명 |
|---|---|---|
| ① 청킹 | Chunking | 긴 문서를 검색 단위(조각)로 쪼갠다 |
| ② 임베딩 | Embedding | 텍스트를 의미를 담은 숫자 벡터로 변환한다 |
| ③ 인덱싱 | Indexing | 청크 + 벡터를 벡터 DB에 저장한다 |
| ④ 검색 | Retrieval | 질문 벡터와 **가장 가까운** 청크를 찾는다 |
| ⑤ 증강 | Augmentation | 검색된 청크를 프롬프트에 끼워 넣는다 |
| ⑥ 생성 | Generation | LLM이 그 근거만으로 답을 만든다 |

### 핵심 개념: 임베딩과 코사인 유사도
- **임베딩**: "숭례문 방화 화재"라는 문장을 `[0.021, -0.044, ...]` 같은 **768개 숫자(벡터)** 로 바꾼 것.
  의미가 비슷한 문장은 벡터 공간에서 **가까운 위치**에 놓인다.
- **코사인 유사도**: 두 벡터가 이루는 각도로 유사도를 잰다. 1에 가까울수록 비슷하다.
  "폭설로 무너졌나?" 라는 질문 벡터는 "방화 화재" 청크 벡터와 (둘 다 '숭례문 붕괴 사건'을 다루므로) 가깝다.

---

## 3. 우리 프로젝트에서의 적용

각 단계가 어떤 파일/함수에 있는지 매핑한다.

### ① 청킹 — [backend/core/chunker.py](../backend/core/chunker.py)
국가유산 원문(`content`)을 **문단(줄바꿈) 기준, 최대 300자**로 자른다.
한 문단이 길면 문장 단위로 다시 누적한다.

```python
# chunk_text(text, max_len=300)
paragraphs = [p for p in text.splitlines() if p.strip()]
for para in paragraphs:
    if len(para) <= max_len:
        chunks.append(para)
    else:
        chunks.extend(_pack_sentences(_split_sentences(para), max_len))
```

> **왜 쪼개나?** 문서 전체를 통째로 임베딩하면 의미가 뭉개지고, 검색 시 불필요한 내용까지 딸려온다.
> 적당한 크기의 청크가 "검색의 정확도"와 "문맥 보존" 사이의 균형점이다.

### ② 임베딩 — [backend/api/embeddings.py](../backend/api/embeddings.py)
텍스트를 **Gemini `gemini-embedding-001`** 으로 768차원 벡터로 변환한다.
provider 추상화로 OpenAI(`text-embedding-3-small`)로도 교체 가능.

```python
# embed_text("숭례문은 한양도성의 정문이다.") -> [0.013, -0.027, ... ] (768개)
embed_texts([t])  # REST 호출, 429 시 지수 백오프 재시도
```

같은 모델을 **사전 준비(문서)** 와 **질의(질문)** 양쪽에 똑같이 써야 같은 벡터 공간에서 비교가 된다.

### ③ 인덱싱 — [backend/core/vector_store.py](../backend/core/vector_store.py) + [docker-compose.yml](../docker-compose.yml)
**PostgreSQL + pgvector**(Docker)에 청크와 벡터를 저장한다.

```sql
CREATE TABLE heritage_chunks (
    id            SERIAL PRIMARY KEY,
    source_type   TEXT,            -- 'heritage' | 'term'
    heritage_name TEXT,
    term          TEXT,
    chunk_index   INT,
    content       TEXT,            -- 청크 원문
    image_url     TEXT,
    embedding     vector(768)      -- ← pgvector 타입
);
```

적재는 [backend/ingest.py](../backend/ingest.py)가 담당한다.
국가유산 원문 청크 + **용어 사전**도 함께 임베딩해 넣는다(`source_type`으로 구분).

```bash
python ingest.py              # 초기화 + 용어 + 기본 유산
python ingest.py --bulk 11 25 # 국보 25건 추가 적재
```

### ④ 검색(Retrieval) — [backend/core/vector_store.py](../backend/core/vector_store.py) `search()`
질문 벡터와 **코사인 거리(`<=>`)** 가 가장 작은 청크 top-k를 가져온다.

```sql
SELECT content, source_type, heritage_name, term, image_url,
       1 - (embedding <=> %s::vector) AS similarity   -- 유사도 = 1 - 거리
FROM heritage_chunks
ORDER BY embedding <=> %s::vector                      -- 가까운 순
LIMIT %s;
```

> `<=>` 는 pgvector가 제공하는 **코사인 거리 연산자**. 0이면 동일, 클수록 다르다.
> `1 - 거리`로 "유사도"(1에 가까울수록 비슷)로 바꿔 응답에 표시한다.

### ④-심화: 하이브리드 검색 — [backend/core/pipeline.py](../backend/core/pipeline.py) `_hybrid_retrieve()`
순수 벡터 검색만 쓰면 "A랑 B 비교해줘" 질문에서 **유사도 높은 한쪽 유산에 청크가 쏠리는** 문제가 있다.
그래서 세 신호를 결합한다.

```python
# 1) 이름 필터: 질문에 언급된 유산을 감지해 유산별로 균형 있게
mentioned = _detect_mentioned_heritages(question, names)   # "숭례문", "수원 화성" 감지
for hname in mentioned:
    add(vector_store.search(q_vec, top_k=per, heritage_name=hname))  # 유산별 한정 검색

# 2) 전역 벡터 검색 (의미 유사)
add(vector_store.search(q_vec, top_k=top_k))

# 3) 키워드 ILIKE 보강
add(vector_store.keyword_search(tokens, limit=3))
# content 중복 제거 후 우선순위 병합
```

| 신호 | 역할 |
|---|---|
| 벡터(의미) | "폭설로 무너졌나?" ↔ "방화 화재" 처럼 표현이 달라도 의미로 매칭 |
| 이름 필터 | 비교 질문에서 양쪽 유산 청크를 **균형 있게** 확보 |
| 키워드 | 고유명사/전문용어 정확 매칭 보강 |

### ⑤ 증강(Augmentation) — [backend/core/prompt_builder.py](../backend/core/prompt_builder.py) `build_rag_prompt()`
검색된 청크를 `[검색된 자료]` 블록으로 시스템 프롬프트에 끼워 넣고, **환각 방지 규칙**을 명시한다.

```
당신은 국가유산 전문 해설사입니다. 아래 [검색된 자료]에 근거해서만 답합니다.
규칙:
1. 자료에 있는 사실만 사용한다. 없으면 "제공된 자료에서는 확인되지 않습니다"라고 답한다.
2. 질문의 전제가 자료와 다르면 정중히 바로잡는다. (예: 폭설 → 실제로는 방화)
...
[검색된 자료]
1. [서울 숭례문] 2008년 숭례문 방화 사건은 ...
2. [서울 숭례문] Ο 숭례문 방화 화재(2008.2.10) ...
```

### ⑥ 생성(Generation) — [backend/core/pipeline.py](../backend/core/pipeline.py) `rag_answer()`
조립한 프롬프트로 LLM을 호출하고, 답변 + 대표 이미지 + 근거 청크를 묶어 반환한다.

```python
def rag_answer(question, lang="ko", top_k=5):
    q_vec = embed_text(question)                       # ② 질문 임베딩
    hits  = _hybrid_retrieve(question, q_vec, top_k)   # ④ 검색
    context = "\n".join(f"{i}. [{label}] {h.content}" for ...)  # ⑤ 증강
    answer = call_llm(build_rag_prompt(context, lang), question) # ⑥ 생성
    return RagResult(answer, sources, image_url, ...)
```

이 결과는 [backend/main.py](../backend/main.py)의 `POST /api/rag` 로 노출되고,
프론트엔드([frontend/src/App.jsx](../frontend/src/App.jsx))의 카카오톡 스타일 챗에서 표시된다.

---

## 4. 전체 데이터 흐름 (질문 → 답변)

```
사용자: "숭례문은 폭설로 무너진 적 있어?"
   │
   ▼  ② embed_text()  (embeddings.py)
질문 벡터 [768차원]
   │
   ▼  ④ _hybrid_retrieve()  (pipeline.py)
   │     ├ 이름 필터: "숭례문" 감지 → 숭례문 청크 한정 검색
   │     ├ 전역 벡터: <=> 코사인 검색  (vector_store.search)
   │     └ 키워드: ILIKE 보강
   ▼
검색된 청크 (유사도순)
   1. [서울 숭례문] 2008년 숭례문 방화 사건은...   (0.725)
   2. [서울 숭례문] 방화 화재로 누각 2층 지붕이...  (0.706)
   │
   ▼  ⑤ build_rag_prompt()  (prompt_builder.py)
[검색된 자료] + 환각방지 규칙이 담긴 시스템 프롬프트
   │
   ▼  ⑥ call_llm()  (llm_api.py)
답변: "아닙니다, 숭례문은 폭설로 무너진 적이 없습니다.
       2008년 2월 10일 방화 화재로..."
   + 이미지(숭례문) + 근거 청크(출처/유사도)
```

→ **잘못된 전제("폭설")를 자료 근거로 정정**했다. 이것이 RAG의 핵심 가치다.

---

## 5. 직접 확인해보기

```bash
# 1) DB 적재 현황
#    헬스 체크
curl http://localhost:8000/

# 2) RAG 질문 (정정 시나리오)
curl -X POST http://localhost:8000/api/rag \
  -H "Content-Type: application/json" \
  -d '{"question":"숭례문은 폭설로 무너진 적 있어?","lang":"ko","top_k":5}'

# 3) 비교 질문 (하이브리드 검색)
curl -X POST http://localhost:8000/api/rag \
  -H "Content-Type: application/json" \
  -d '{"question":"숭례문이랑 수원 화성 비교해줘","lang":"ko","top_k":6}'

# 4) 미적재 정보 (환각 방지)
curl -X POST http://localhost:8000/api/rag \
  -H "Content-Type: application/json" \
  -d '{"question":"경복궁 근정전 높이는?","lang":"ko"}'
# → "제공된 자료에서는 확인되지 않습니다."
```

프론트엔드(http://localhost:5173)에서는 답변 아래 **🔎 근거 원문 보기** 토글로,
LLM이 실제로 어떤 청크를 근거로 답했는지(유사도 %까지) 직접 검증할 수 있다.

---

## 6. 우리 RAG의 설계 선택 요약

| 항목 | 선택 | 이유 |
|---|---|---|
| 청크 크기 | 문단 기준 300자 | 문맥 보존 ↔ 검색 정밀도 균형 |
| 임베딩 | gemini-embedding-001 (768d) | provider 추상화로 OpenAI 교체 가능 |
| 벡터 DB | PostgreSQL + pgvector | 별도 인프라 없이 SQL로 코사인 검색 |
| 검색 | 하이브리드(벡터+이름+키워드) | 비교 질문에서 균형 확보 |
| 환각 방지 | 프롬프트 규칙 + "확인되지 않습니다" | 자료 밖 답변 차단, 전제 정정 |
| 출처 노출 | 근거 청크 + 유사도 반환 | 사용자가 직접 근거 검증 |

---

## 7. RAG 위에 얹은 것 — 대화·개인화·비용

기본 RAG(검색→증강→생성) 위에 실사용 품질/비용을 위한 레이어를 더했다.

- **멀티턴(질의 재작성)**: 후속 질문에 지시어("그 둘", "거기")가 있으면 이전 대화로 **독립 검색어로 재작성**한 뒤 검색한다. ([pipeline.py](../backend/core/pipeline.py) `_needs_condense`, `build_condense_prompt`)
- **이미지 의도 게이트**: "보여줘/소개/비교/이름만"일 때만 사진을 띄우고, 사실 질문엔 답만. 상위 개념(예: "원각사")은 개별 유산을 제안. ([pipeline.py](../backend/core/pipeline.py) `_wants_image`)
- **개인화**: 검색된 청크의 분류(category)를 사용자 관심 가중치로 누적해, 생성 프롬프트에 주입. ([user_store.py](../backend/core/user_store.py))
- **비용 최적화**: 단일턴 응답 캐싱 · 단순 질문은 저렴 모델(`flash-lite`) 라우팅 · condense 게이팅 · 이력 다이어트.
- **관측성(정량 평가)**: 요청별 토큰·지연·캐시·모델을 `request_logs`(같은 PostgreSQL)에 기록. LLM 응답의 `usageMetadata`에서 토큰을 포착해, 가드레일·라우팅·캐시가 **실제로 토큰/지연을 줄였는지 `GET /api/metrics`로 증명**한다. ([request_log.py](../backend/core/request_log.py))

> 핵심 원칙: **정확성은 항상 우선**. 캐싱·저렴모델 같은 절감은 "확실히 단순하거나 비개인화인 경우"에만 적용해 답변 품질을 깎지 않는다.

---

## 8. 품질·안전 규칙 (생성 가드레일)

검색이 아무리 좋아도, **생성 단계에서 자료를 어떻게 다루느냐**가 답변의 신뢰성을 좌우한다.
아래 규칙들은 [prompt_builder.py](../backend/core/prompt_builder.py)의 RAG 시스템 프롬프트(`build_rag_prompt`)에
**한 번** 박아 두어, 모든 답변·전체 코퍼스에 일괄 적용된다. (데이터를 한 건씩 고치지 않는다.)

### ① 정확성 · 환각 방지
- [검색된 자료]에 **있는 사실만** 사용한다.
- 자료에 없으면 지어내지 말고 **"제공된 자료에서는 확인되지 않습니다"**.
- 질문의 **전제가 자료와 다르면 정정**한다. (예: "폭설로 무너졌나?" → "방화 화재였다")
- 연도·인물명 등 사실을 **왜곡·추가하지 않는다**.

### ② 사료·고어 안전 (고전 텍스트 오독 방지)
국가유산 자료에는 옛 문체·한문 번역투가 섞여 있어, 그대로 옮기면 현대 독자가 오독한다.
- 옛 표현("A曰B", "~이니/~이라/~하니")은 **현대 한국어로 풀어 쓴다**.
- 특히 **'-이니/-이라'를 인과("때문에")로 곡해하지 않는다** — 옛말에선 '이고/이며'(나열·병렬)인 경우가 많다.
  - 실제 사례: 태조실록 `正南曰崇禮門 俗稱南大門` 을 "숭례문**이니** 남대문"으로 옮기면
    "숭례문이니까 남대문"이라는 **틀린 인과**로 읽힌다. → "정식명은 숭례문, **속칭**은 남대문"(병렬)로 풀어야 정확.
- 옛 기록을 인용할 땐 **원문(한자) + 현대어 뜻**을 함께 제시한다.

### ③ 응답 형태 (간결 · 점진)
- 핵심만 **2~4문장**. 표·긴 목록은 사용자가 "자세히/표로"를 명시할 때만.
- 끝의 추가 제안은 **질문 주제와 직접 이어질 때만**. 동떨어진 제안(명칭을 물었는데 현판 글씨 권유)은 하지 않는다.
- 상위 개념("원각사")은 사진을 보류하고 **개별 유산을 제안**(progressive disclosure).

### ④ 표현 위생
- **이미지는 앱이 자동 표시**하므로 "이미지를 보여줄 수 없다"고 말하지 않는다.
- **'[검색된 자료]', 'N번', '청크'** 같은 내부 구조 표현을 답변에 노출하지 않는다 ("자료에 따르면" 정도로만).

### ⑤ 맥락 · 다국어 · 개인화
- [이전 대화] 지시어("그 둘")를 맥락으로 해석.
- 요청 언어(ko/en/zh/ja)로 답하고 고유명사는 원어 병기.
- 사용자 관심 분야가 있으면 그 측면을 우선하되 간결함은 유지(억지 주입 금지).

> **공통 원칙: 정확성 우선.** 캐싱·저렴모델 라우팅 같은 비용 절감은 "확실히 단순하거나 비개인화인 경우"에만 적용해 품질을 깎지 않는다.

### 검증된 외부 사실 보강 ('카더라' 대응)
국가유산청 원문에 없는 검증 사실은 [knowledge_notes.json](../backend/data/knowledge_notes.json)에
`source_type='note'`로 적재한다(출처 URL 포함). 임베딩엔 본문만 넣고 출처는 마커로 분리해,
**답변엔 출처 '이름'**, **근거 원문엔 클릭 가능한 출처 '링크'** 로 노출한다.
```bash
python ingest.py --notes   # data/knowledge_notes.json 재적재
```

---

### 참고 파일 한눈에 보기
- 청킹: [chunker.py](../backend/core/chunker.py)
- 임베딩: [embeddings.py](../backend/api/embeddings.py)
- 벡터 저장/검색: [vector_store.py](../backend/core/vector_store.py)
- 적재: [ingest.py](../backend/ingest.py)
- RAG 조율/하이브리드: [pipeline.py](../backend/core/pipeline.py)
- 프롬프트: [prompt_builder.py](../backend/core/prompt_builder.py)
- 엔드포인트: [main.py](../backend/main.py)
- 개인화: [user_store.py](../backend/core/user_store.py)
- 챗 UI: [App.jsx](../frontend/src/App.jsx)
