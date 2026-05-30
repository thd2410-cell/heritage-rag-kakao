# National Heritage AI Docent Chatbot

국가유산청/국가유산포털의 공식 데이터를 근거로 답변하는 국가유산 AI 해설 챗봇 MVP입니다. 운영 목표 구조는 Next.js Frontend, Spring Boot Backend/BFF, FastAPI AI Server, PostgreSQL + pgvector, Redis, Docker/Kubernetes입니다.

샘플 데이터는 테스트용입니다. 실제 서비스 출시 전에는 국가유산청/국가유산포털 공식 원천 데이터로 교체하고, 이미지 이용 조건을 검수해야 합니다.

## Architecture

```text
Browser
  -> Next.js Frontend :3000
  -> Spring Boot Backend/BFF :8081
       -> FastAPI AI Server :8000
            -> Input Guardrail
            -> Language Detection
            -> Entity Normalization
            -> Intent Routing
            -> Hybrid Retrieval
            -> Reranking
            -> Answer Generation
            -> Claim Verification
            -> Output Guardrail
       -> PostgreSQL + pgvector
       -> Redis
```

## Run

```bash
docker compose up --build
```

서비스 URL:

- Frontend: http://127.0.0.1:3000
- Spring Backend: http://127.0.0.1:8081/api/health
- AI Server: http://127.0.0.1:8000/health

## Environment

`.env.example` 기준:

```text
DATABASE_URL=postgresql+psycopg://heritage:heritage@postgres:5432/heritage
REDIS_URL=redis://redis:6379/0
AI_SERVER_URL=http://ai-server:8000
NEXT_PUBLIC_BACKEND_URL=http://localhost:8081
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
LLM_PROVIDER=dummy
EMBEDDING_PROVIDER=mock
AUTO_CONFIRM_ENTITY_THRESHOLD=0.86
CONFIRM_ENTITY_THRESHOLD=0.78
DEFAULT_TOP_K=8
```

OpenAI를 사용할 때:

```text
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4.1-mini
LLM_PROVIDER=openai
```

테스트 환경은 `LLM_PROVIDER=dummy`로 동작하므로 API key가 없어도 깨지지 않습니다.

## Sample Data

기본 샘플 적재:

```bash
curl -X POST http://127.0.0.1:8081/api/ingest/sample
```

공식 데이터 파일 적재:

```bash
curl -X POST http://127.0.0.1:8081/api/ingest/official \
  -H "Content-Type: application/json" \
  -d '{"path":"/app/ai-server/data/import/official_sample.json","chunk_size":900}'
```

JSON/CSV 적재 포맷:

```text
entities, aliases, documents, relations, images
```

Docker에서는 `./ai-server/data`가 `/app/ai-server/data`로 마운트됩니다.

## Chat API

```bash
curl -X POST http://127.0.0.1:8081/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query":"경북궁 설명해줘","audience":"general"}'
```

응답에는 `answer`, `entities`, `citations`, `images`, `route`, `safety_flags`가 포함됩니다.

## KHS Official OpenAPI And Images

국가유산청 OpenAPI 안내:
https://www.khs.go.kr/html/HtmlPage.do?pg=/publicinfo/pbinfo3_0202.jsp&mn=NS_04_04_03

KHS 이미지 OpenAPI(`SearchImageOpenapi.do`) 결과를 `heritage_images` 테이블에 저장하고, `/chat` 응답의 `images` 배열로 내려보냅니다. Next.js UI는 이미지가 있으면 답변 아래에 썸네일, 캡션, 이용 조건을 표시합니다.

KHS 이미지 직접 적재:

```bash
curl -X POST http://127.0.0.1:8000/ingest/khs/images \
  -H "Content-Type: application/json" \
  -d '{"heritage_entity_id":"official-gyeongbokgung","ccba_kdcd":"11","ccba_asno":"01170000","ccba_ctcd":"11"}'
```

`ccba_kdcd`, `ccba_asno`, `ccba_ctcd`는 KHS 목록/상세 API에서 내려오는 코드입니다. 대량 운영 적재는 목록/상세 API로 이 코드들을 먼저 수집한 뒤, 각 엔티티별로 이미지 API를 호출하는 방식으로 확장해야 합니다.

KHS 목록/상세/이미지를 한 번에 끊어서 적재:

```bash
curl -X POST http://127.0.0.1:8081/api/ingest/khs/bulk \
  -H "Content-Type: application/json" \
  -d '{"ccba_ctcds":["11"],"page_unit":20,"max_pages":1,"limit":20,"include_images":true}'
```

운영 대량 적재는 `ccba_ctcds`를 시도코드별로 나눠 여러 번 실행하는 방식이 안전합니다. 예를 들어 서울 `11`을 먼저 검증한 뒤 부산, 대구 등으로 확장합니다.

## Entity Normalization

RAG 전에 엔티티 정규화를 수행합니다.

- exact alias matching
- case-insensitive matching
- 공백/하이픈/구두점 제거
- Unicode NFKC
- 한글 자모 분해 기반 fuzzy matching
- romanization, hanja, multilingual alias
- STT 오인식 후보
- confidence score 및 confirmation flag

예시:

- `경북궁` -> `경복궁`
- `gyeongbokgung` -> `경복궁`
- `Gyeongbok Palace` -> `경복궁`
- `景福宮` -> `경복궁`

## Hybrid RAG

검색은 벡터 검색만 사용하지 않습니다.

```text
final_score =
  0.35 * keyword_score +
  0.35 * vector_score +
  0.15 * entity_match_bonus +
  0.10 * trust_level_bonus +
  0.05 * relation_bonus
```

S1/S2 근거를 역사 답변의 기본 근거로 사용하고, S4는 기본 답변 근거에서 제외합니다.

## Guardrails And Verification

- prompt injection 탐지
- 출처 무시 요청 탐지
- 위험/혐오/폭력 요청 차단
- citation 없는 역사 주장 차단
- evidence에 없는 연도/인물/장소 claim 탐지
- 시스템 프롬프트/API key/stack trace 노출 차단

## Evaluation

```bash
curl -X POST http://127.0.0.1:8000/eval/run
```

측정 대상:

- entity normalization accuracy
- retrieval recall
- citation rate
- unsupported claim rate
- guardrail detection rate
- average latency

## Tests

```bash
pytest
```

## Production Notes

현재 MVP 한계:

- 실제 대량 KHS 데이터 전체 수집기는 아직 별도 배치 작업으로 확장해야 합니다.
- pgvector SQL similarity와 PostgreSQL FTS는 adapter 경계가 있으며, 운영 검색 품질 튜닝이 필요합니다.
- Redis cache policy, auth, rate limit, observability는 운영 수준으로 강화해야 합니다.
- 이미지 이용 조건은 공식 API 응답 기준으로 저장하지만, 공개 서비스 전 별도 법무/정책 검수가 필요합니다.

향후 확장:

- OpenSearch/Elasticsearch
- Qdrant/Milvus
- Neo4j
- 지도 API
- STT/TTS
- Kubernetes Helm chart
- Prometheus/Grafana dashboard
