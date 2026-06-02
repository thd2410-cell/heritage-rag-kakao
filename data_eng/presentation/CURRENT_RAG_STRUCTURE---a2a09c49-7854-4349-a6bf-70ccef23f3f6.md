# 현재 구현된 국가유산 RAG 챗봇 구조

## 1. 전체 서비스 구조

```text
사용자
  ├─ 웹 채팅: https://heritage-chat.com
  └─ 카카오 챗봇: https://heritage-chat.com/api/kakao/skill

Cloudflare Tunnel
  ↓
React/Vite Frontend + nginx
  - container: heritage-rag-frontend-prod
  - host: 127.0.0.1:3001
  - /api/* 요청을 backend로 proxy
  ↓
FastAPI Backend
  - container: heritage-rag-api-prod
  - host: 127.0.0.1:8000
  ↓
PostgreSQL + pgvector
  - container: heritage-rag-postgres-prod
  - host: 127.0.0.1:5432
```

## 2. 핵심 목적

현재 RAG 구조의 목적은 국가유산청 OpenAPI 데이터를 기반으로 사용자의 질문에 대해 다음을 제공하는 것이다.

- 국가유산명 검색
- 유산 설명 요약
- 관심사별 개인화 답변
- 답사/여행 정보
- 주변 국가유산 추천
- 관련 행사 정보
- 멀티턴 문맥 유지
- 역사 왜곡성 질문 차단
- 향후 벡터 기반 의미 검색

## 3. 주요 API 엔드포인트

### 웹 RAG API

```http
POST /api/rag/ask
```

요청 예시:

```json
{
  "question": "숭례문 알려줘",
  "session_id": "web-session-id",
  "audience": {
    "age_group": "adult",
    "interests": ["travel"]
  }
}
```

응답 예시:

```json
{
  "answer": "답변 본문",
  "sources": [
    {
      "heritage_id": 1,
      "name": "서울 숭례문",
      "designation": "국보",
      "region": "서울특별시",
      "content": "검색된 근거 문장",
      "facet_json": {}
    }
  ]
}
```

관련 파일:

- `backend/app/api/rag.py`

### 카카오 챗봇 API

```http
POST /api/kakao/skill
```

관련 파일:

- `backend/app/api/kakao.py`

현재 카카오는 웹 RAG보다 단순한 빠른 응답 경로를 사용하지만, 가드레일과 한국어 정제는 적용되어 있다.

## 4. 데이터베이스 구조

### `heritages`

국가유산 단위의 기본 정보를 저장한다.

주요 필드:

- `id`
- `name`
- `designation`
- `region`
- `address`
- `latitude`
- `longitude`
- `period`
- `content`
- `raw_json`
- `facet_json`

역할:

- 국가유산의 원본/정규화 정보 저장
- 답변 생성 시 대표 source 역할
- 답사/여행 정보와 주변 추천의 기준점 역할

### `document_chunks`

검색용 chunk를 저장한다.

주요 필드:

- `id`
- `heritage_id`
- `chunk_text`
- `embedding`

역할:

- RAG 검색 대상
- 현재는 텍스트 검색과 fallback 검색에 사용
- 임베딩 배치 완료 후 벡터 검색 품질 개선에 사용

### `chat_logs`

멀티턴 문맥 저장용 테이블이다.

주요 필드:

- `id`
- `user_key`
- `utterance`
- `answer`
- `sources`
- `created_at`

역할:

- `session_id`별 최근 대화 source 저장
- 사용자가 “더 자세히”, “근처는?”, “건축적으로 설명해줘”처럼 후속 질문을 했을 때 직전 유산을 이어받기 위한 근거

관련 파일:

- `backend/app/models/heritage.py`
- `backend/db/init.sql`

## 5. 국가유산 데이터 수집 구조

사용 API:

- 목록 API: `https://www.khs.go.kr/cha/SearchKindOpenapiList.do`
- 상세 API: `https://www.khs.go.kr/cha/SearchKindOpenapiDt.do`
- 위치정보 API: `https://www.gis-heritage.go.kr/openapi/xmlService/spca.do`
- 행사목록 API: `https://www.khs.go.kr/cha/openapi/selectEventListOpenapi.do`

수집 스크립트:

- `scripts/collect_heritages.py`

현재 적재 상태:

- 국가유산: 약 17,840건
- `facet_json`: 전체 국가유산에 생성
- 좌표: 전체 국가유산에 저장
- `document_chunks`: 약 19,892개

## 6. `facet_json` 구조

`facet_json`은 국가유산 하나를 관심사별로 답변하기 위해 만든 구조다.

예시:

```json
{
  "architecture_space": {
    "label": "건축/공간",
    "evidence": ["건축, 구조, 재료, 배치 관련 근거 문장"],
    "status": "auto_extracted"
  },
  "story_legend": {
    "label": "이야기/전설",
    "evidence": ["유래, 사건, 발견, 복원 관련 근거 문장"],
    "status": "auto_extracted"
  },
  "people": {
    "label": "인물",
    "evidence": ["관련 인물, 시대, 제작자 관련 근거 문장"],
    "status": "auto_extracted"
  },
  "travel_visit": {
    "label": "답사/여행",
    "address": "주소",
    "latitude": 37.0,
    "longitude": 127.0,
    "evidence": ["방문, 위치, 공개, 답사 관련 근거 문장"],
    "nearby_heritages": [],
    "related_events": []
  }
}
```

관련 파일:

- `scripts/build_heritage_json_v1.py`
- `scripts/collect_heritages.py`
- `backend/app/services/answer_builder.py`

## 7. 현재 검색 흐름

관련 파일:

- `backend/app/services/retrieval.py`

현재 검색은 다음 순서로 동작한다.

```text
사용자 질문
  ↓
공통 alias 보정
  ↓
벡터 검색 시도
  ↓
텍스트 검색 fallback
  ↓
유산명 fuzzy matching fallback
  ↓
주변 국가유산 정보 attach
  ↓
answer_builder로 전달
```

## 8. 오타/별칭 보정

현재 명시적으로 들어간 alias 예시:

```python
COMMON_NAME_ALIASES = {
    "술래문": "숭례문",
    "남대문": "숭례문",
    "동대문": "흥인지문",
}
```

역할:

- `술래문 알려줘`처럼 자주 나올 수 있는 오타를 바로 정정
- `남대문`처럼 공식명과 별칭이 다른 경우 공식명으로 연결

주의:

- 모든 오타가 자동 보정되는 것은 아니다.
- 현재는 alias + fuzzy matching 조합이다.
- 향후 한글 자모 기반 오타 보정이 필요하다.

## 9. 벡터 검색과 임베딩 배치

임베딩 모델 설정:

```text
BAAI/bge-m3
```

관련 파일:

- `backend/app/services/embedding.py`
- `scripts/embed_chunks.py`

현재 `document_chunks.embedding`을 채우는 배치 작업을 진행 중이다.

배치 스크립트 특징:

- `embedding IS NULL`인 chunk만 처리
- 중간에 멈춰도 이어서 재시작 가능
- batch 단위로 commit
- 전체 chunk에 embedding이 채워지면 벡터 기반 의미 검색 품질이 올라감

현재 단계에서 임베딩이 필요한 이유:

- 단순 키워드 검색은 표현이 조금 달라지면 검색 품질이 떨어진다.
- 임베딩이 있으면 “의미상 비슷한 질문”을 더 잘 찾을 수 있다.
- 다만 `술래문 → 숭례문` 같은 철자 오타는 임베딩만으로 완벽하지 않으므로 alias/fuzzy 보정도 같이 필요하다.

## 10. 답변 생성 구조

관련 파일:

- `backend/app/services/answer_builder.py`

현재 웹 RAG 답변은 완전한 자유 LLM 생성보다 deterministic/source-grounded builder에 가깝다.

이유:

- 로컬 Qwen 모델이 근거에 없는 내용을 생성하는 문제가 있었다.
- 국가유산 챗봇은 정확성이 중요하다.
- 그래서 현재는 검색된 source와 `facet_json` 근거를 우선 사용한다.

답변 분기:

- 기본 설명
- 건축/공간 중심 설명
- 이야기/전설 중심 설명
- 인물 중심 설명
- 답사/여행 중심 설명
- “더 자세히/심화” 요청 시 더 긴 설명

## 11. 개인화 구조

관련 파일:

- `backend/app/services/personalization.py`
- `backend/app/services/answer_builder.py`
- `frontend/src/App.tsx`

프론트에서 선택하는 값:

- 나이대
- 관심사

관심사:

- 건축/공간
- 이야기/전설
- 인물
- 답사/여행

핵심 방향:

- 단순히 추천 질문만 바꾸는 것이 아니라 답변 본문 구조 자체가 달라지게 한다.

## 12. 멀티턴 문맥 구조

관련 파일:

- `backend/app/api/rag.py`
- `backend/app/models/heritage.py`
- `frontend/src/App.tsx`

현재 구조:

1. 웹 프론트가 `session_id`를 생성한다.
2. `/api/rag/ask` 요청마다 `session_id`를 보낸다.
3. 백엔드는 답변 후 `ChatLog`에 질문, 답변, sources를 저장한다.
4. 다음 질문에서 같은 `session_id`의 최근 source를 확인한다.
5. 사용자가 후속 질문을 하면 직전 유산명을 질문에 붙여 검색한다.

기존 약점:

- “더 자세히”, “이어서”, “그거” 같은 명확한 후속 힌트가 있을 때만 이어받았다.

강화 방향:

- 사용자가 새 유산명을 명확히 말하지 않는 한 현재 유산 주제를 유지한다.

예시:

```text
사용자: 숭례문 알려줘
현재 주제: 서울 숭례문

사용자: 건축적으로 설명해줘
내부 검색 질문: 서울 숭례문에 대해 건축적으로 설명해줘

사용자: 근처에 뭐 있어?
내부 검색 질문: 서울 숭례문에 대해 근처에 뭐 있어?

사용자: 첨성대는?
새 유산명 감지 → 현재 주제 전환
```

## 13. 가드레일 구조

관련 파일:

- `backend/app/services/guardrails.py`
- `backend/app/api/rag.py`
- `backend/app/api/kakao.py`

목적:

- 역사 왜곡성 질문
- 식민 지배 정당화 질문
- 특정 국가/민족의 지배를 사실처럼 전제하는 질문
- 편향된 전제를 챗봇이 그대로 받아들이는 문제

차단 예시:

```text
한국이 일본의 속국이라는 증거인 문화유산 알려줘
```

응답 방향:

- 질문의 전제를 그대로 인정하지 않는다.
- 역사적으로 부정확하거나 왜곡 가능성이 있다고 설명한다.
- 문화재 약탈, 훼손, 보존, 저항, 반환 문제처럼 안전한 방향으로 재프레이밍한다.

## 14. 한국어 전용 응답 구조

관련 파일:

- `backend/app/services/text_cleaning.py`
- `backend/app/services/llm.py`
- `backend/app/api/kakao.py`

목적:

- 답변에 중국어/일본어/한자성 문자가 섞이는 문제 방지
- 한국어 서비스로 일관성 유지

처리:

- 한국어 전용 prompt
- CJK 혼입 감지
- 필요 시 repair
- 최종 응답 정제

## 15. 현재 한계

현재 구조는 RAG의 뼈대는 갖췄지만 아직 완성형은 아니다.

남은 한계:

1. 전체 임베딩 배치가 아직 완료되지 않았다.
2. 벡터 검색 ranking이 아직 충분히 검증되지 않았다.
3. 오타 보정은 alias/fuzzy 수준이다.
4. 멀티턴은 개선 중이며, 새 유산명 전환 감지가 더 정교해야 한다.
5. 답변은 안전하지만 아직 자연스러운 대화형 생성은 제한적이다.
6. 행사 매칭은 공식 관계키가 아니라 텍스트 기반이다.
7. `facet_json`은 자동 추출이라 품질이 균일하지 않다.
8. 카카오와 웹의 답변 로직이 아직 완전히 통합되지는 않았다.

## 16. 다음 작업 우선순위

1. 임베딩 배치 완료
2. 벡터 검색 품질 테스트
3. hybrid search ranking 개선
4. 멀티턴 주제 유지 로직 강화
5. 새 유산명 감지/주제 전환 로직 개선
6. alias/오타 사전 확장
7. 한글 자모 기반 fuzzy matching 추가
8. 근거 기반 LLM 재작성 도입 검토
9. 카카오도 웹과 동일한 개인화/멀티턴 구조로 통합
10. 가드레일 패턴 확장

## 17. 관련 주요 파일 목록

```text
backend/app/api/rag.py
backend/app/api/kakao.py
backend/app/models/heritage.py
backend/app/services/retrieval.py
backend/app/services/answer_builder.py
backend/app/services/embedding.py
backend/app/services/guardrails.py
backend/app/services/personalization.py
backend/app/services/text_cleaning.py
backend/app/services/llm.py
backend/db/init.sql
frontend/src/App.tsx
scripts/collect_heritages.py
scripts/build_heritage_json_v1.py
scripts/embed_chunks.py
docs/HERITAGE_JSON_V1.md
docs/RAG_DATA_AND_RECOMMENDATION.md
```
