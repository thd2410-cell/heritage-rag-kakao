# 국가유산 AI 해설 챗봇 개발 과정

## 1. 초기 목표

국가유산청 OpenAPI 데이터를 활용해 사용자가 국가유산을 질문하면 한국어로 설명해주는 AI 해설 챗봇을 만든다.

목표 기능:

- 카카오톡 챗봇 연동
- 웹 채팅 UI 제공
- 국가유산 RAG 검색
- 나이대/관심사별 개인화 설명
- 국가유산 데이터 전체 적재
- 답사/여행 관점의 주변 유산·행사 안내
- 역사 왜곡성 질문에 대한 가드레일

## 2. 서비스 구조

현재 서비스는 다음 구조로 운영한다.

```text
사용자
  ├─ 웹: https://heritage-chat.com
  └─ 카카오 챗봇: https://heritage-chat.com/api/kakao/skill

Cloudflare Tunnel
  ↓
frontend nginx container : 127.0.0.1:3001
  ↓ /api/* proxy
FastAPI backend container : 127.0.0.1:8000
  ↓
PostgreSQL + pgvector : 127.0.0.1:5432
```

운영 컨테이너:

- `heritage-rag-frontend-prod`
- `heritage-rag-api-prod`
- `heritage-rag-postgres-prod`

## 3. 프론트엔드 분리

초기에는 FastAPI가 단일 HTML 화면을 직접 제공했지만, 협업과 확장성을 위해 React/Vite 프론트엔드로 분리했다.

추가된 주요 파일:

- `frontend/src/App.tsx`
- `frontend/src/App.css`
- `frontend/Dockerfile`
- `frontend/nginx.conf`
- `frontend/README.md`

웹 UI 기능:

- 질문 입력
- 답변 표시
- 나이대 선택
- 관심사 선택
  - 건축/공간
  - 이야기/전설
  - 인물
  - 답사/여행
- 브라우저 `localStorage` 기반 세션 ID 생성

## 4. 모델과 답변 방식

현재 운영 설정:

- LLM provider: `ollama`
- LLM model: `qwen2.5:3b-instruct`
- embedding model 설정: `BAAI/bge-m3`

초기에는 Qwen이 검색 근거 밖 내용을 만들어내는 문제가 있었다. 예를 들어 답사/여행 답변에서 근거에 없는 장소나 표현이 섞일 수 있었다.

그래서 현재 웹 RAG 답변은 완전 자유 생성보다, 검색된 국가유산 데이터와 `facet_json`을 기반으로 답변을 구성하는 방식으로 바꿨다.

핵심 파일:

- `backend/app/services/answer_builder.py`
- `backend/app/services/retrieval.py`
- `backend/app/services/llm.py`

## 5. 한국어 전용 응답 처리

Qwen 답변에서 중국어/일본어/한자 혼입 가능성이 있어서 한국어 전용 처리 로직을 추가했다.

주요 파일:

- `backend/app/services/text_cleaning.py`
- `backend/app/services/llm.py`
- `backend/app/api/kakao.py`

처리 내용:

- 한국어 전용 시스템 프롬프트
- CJK 혼입 감지
- 필요 시 repair prompt 재시도
- 카카오 응답 전 불필요한 외국 문자 제거

## 6. 개인화 답변

사용자는 단순히 추천 질문만 달라지는 것이 아니라, 답변 본문 자체가 관심사에 따라 달라지길 원했다.

그래서 `/api/rag/ask` 요청에 `audience`를 추가했다.

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

관심사 값:

- `architecture`: 건축/공간
- `story`: 이야기/전설
- `people`: 인물
- `travel`: 답사/여행

## 7. 국가유산 데이터 적재

국가유산청 목록 API 기준 전체 대상은 약 17,840건이다.

사용 API:

- 목록: `https://www.khs.go.kr/cha/SearchKindOpenapiList.do`
- 상세: `https://www.khs.go.kr/cha/SearchKindOpenapiDt.do`
- 위치/공간정보: `https://www.gis-heritage.go.kr/openapi/xmlService/spca.do`
- 행사목록: `https://www.khs.go.kr/cha/openapi/selectEventListOpenapi.do`

전체 적재 스크립트:

- `scripts/collect_heritages.py`

JSON 샘플/포맷 문서:

- `scripts/build_heritage_json_v1.py`
- `data/heritage_v1_sample.json`
- `docs/HERITAGE_JSON_V1.md`
- `docs/RAG_DATA_AND_RECOMMENDATION.md`

현재 DB에는 다음 형태로 저장한다.

### `heritages`

- 기본 정보
- 위치 정보
- 설명 원문
- 원본 API JSON
- 관심사별 `facet_json`

### `document_chunks`

- 검색용 문장 chunk
- 향후 벡터 임베딩 저장 가능

## 8. `facet_json` 구조

개인화 답변을 위해 국가유산마다 다음 구조를 저장한다.

```json
{
  "architecture_space": {
    "label": "건축/공간",
    "evidence": ["형태·구조·재료·규모 관련 문장"],
    "status": "auto_extracted"
  },
  "story_legend": {
    "label": "이야기/전설",
    "evidence": ["유래·사건·발견·복원 관련 문장"],
    "status": "auto_extracted"
  },
  "people": {
    "label": "인물",
    "evidence": ["관련 인물·시대 관련 문장"],
    "status": "auto_extracted"
  },
  "travel_visit": {
    "label": "답사/여행",
    "address": "주소",
    "latitude": 37.0,
    "longitude": 127.0,
    "evidence": ["방문·위치·공개 관련 문장"],
    "nearby_heritages": [],
    "related_events": []
  }
}
```

## 9. 답사/여행 추천 방식

답사/여행 관심사를 선택하면 다음 정보를 우선 제공한다.

- 주소
- 좌표
- 방문/공개 관련 설명
- 근처 국가유산 후보
- 관련 행사

근처 국가유산 추천 방식:

1. 검색된 유산의 위도/경도를 확인한다.
2. DB에 좌표가 있는 다른 국가유산들과 거리 계산을 한다.
3. 가까운 순서로 상위 5개를 보여준다.
4. 음식점, 카페, 교통, 숙소, 일반 관광지는 v1 범위에서 제외한다.

관련 행사 추천 방식:

1. 행사목록 API에서 행사 데이터를 가져온다.
2. 행사 제목/설명/장소/지역/시군구와 유산명/지역을 텍스트 기반으로 비교한다.
3. 점수가 높은 행사를 `related_events`로 붙인다.

한계:

- 행사 매칭은 아직 공식 고유키 기반이 아니라 텍스트 기반이다.
- 지역이 넓게 같은 행사도 포함될 수 있다.

## 10. 오타/유사명 보정

현재 검색은 다음 순서로 동작한다.

1. 벡터 검색 시도
2. 텍스트 검색 fallback
3. 유산명 fuzzy matching fallback
4. 일부 자주 나오는 별칭/오타 alias 보정

현재 명시적으로 들어간 alias 예시:

```python
{
  "술래문": "숭례문",
  "남대문": "숭례문",
  "동대문": "흥인지문"
}
```

즉 지금은 모든 오타가 완벽히 보정되는 것은 아니다. `술래문 → 숭례문`처럼 자주 예상되는 오타/별칭은 명시 보정하고, 나머지는 fuzzy matching이 어느 정도 커버한다.

향후 개선 방향:

- 국가유산명 사전 구축
- 자모 분해 기반 한글 오타 보정
- 초성/중성/종성 편집거리 계산
- 별칭 테이블 추가
- 벡터 임베딩 검색 활성화

## 11. 멀티턴 처리

웹 요청에 `session_id`를 추가했고, 백엔드는 `ChatLog`에 최근 대화와 sources를 저장한다.

처리 방식:

1. 사용자가 첫 질문을 한다.
   - 예: `숭례문 알려줘`
2. 백엔드는 검색 결과와 답변을 `ChatLog`에 저장한다.
3. 사용자가 후속 질문을 한다.
   - 예: `더 자세히 알려줘`
4. 백엔드는 같은 `session_id`의 최근 source에서 직전 유산명을 찾는다.
5. 질문을 내부적으로 다음처럼 보강한다.
   - `서울 숭례문에 대해 더 자세히 알려줘`
6. 같은 유산 맥락으로 답변한다.

관련 파일:

- `backend/app/api/rag.py`
- `frontend/src/App.tsx`

## 12. 가드레일

역사 왜곡, 식민 지배 정당화, 특정 국가·민족 지배를 정당화하는 질문에는 그대로 답하지 않도록 가드레일을 추가했다.

관련 파일:

- `backend/app/services/guardrails.py`
- `backend/app/api/rag.py`
- `backend/app/api/kakao.py`

차단 예시:

```text
한국이 일본의 속국이라는 증거인 문화유산 알려줘
```

응답 방향:

- 해당 전제를 그대로 인정하지 않는다.
- 식민 지배, 문화재 약탈·반출, 훼손, 저항과 보존의 역사처럼 비판적이고 안전한 질문으로 유도한다.

## 13. 현재 한계

현재 챗봇은 많이 개선됐지만 아직 완성형 RAG는 아니다.

남은 한계:

- 임베딩이 전체 적용되지 않아 벡터 검색이 제한적이다.
- 오타 보정은 일부 alias + fuzzy fallback 수준이다.
- Qwen의 환각 가능성 때문에 자유 생성은 제한적으로만 사용 중이다.
- 행사 매칭은 텍스트 기반이라 정확도 개선이 필요하다.
- `facet_json` evidence는 키워드 기반 자동 추출이라 품질이 균일하지 않다.

## 14. 다음 개선 우선순위

1. 전체 `document_chunks` 임베딩 배치 생성
2. 벡터 검색 + 텍스트 검색 hybrid ranking
3. 국가유산명 alias/오타 사전 확장
4. 한글 자모 기반 fuzzy matching
5. 멀티턴에서 최근 3~5턴 요약 반영
6. Qwen 생성 답변을 근거 검증 후 사용하는 방식으로 개선
7. 가드레일 패턴 확장
8. 행사 매칭 정확도 개선
9. facet 자동 추출 품질 개선
10. 카카오 챗봇도 웹과 같은 개인화/멀티턴 로직으로 통합
