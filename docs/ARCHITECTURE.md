# 시스템 아키텍처 · 다이어그램

> 모든 그림은 **Mermaid**. VS Code의 *Markdown Preview Mermaid Support*(`bierner.markdown-mermaid`) 확장 또는 GitHub에서 렌더링된다.

## 0. 렌더링 테스트
아래 가장 단순한 그림이 **안 보이면 확장/프리뷰 문제**(확장 설치·창 새로고침·VS Code 내장 미리보기 사용), **보이면 정상**이다.

```mermaid
graph TD
  A["테스트"] --> B["정상 렌더링"]
```

- [1. 시스템 아키텍처](#1-시스템-아키텍처)
- [2. ERD](#2-erd-데이터-모델)
- [3. RAG 질의 플로우](#3-rag-질의-플로우-apirag)
- [4. 기본 해설 파이프라인](#4-기본-해설-파이프라인-apiheritage)
- [5. 데이터 적재 파이프라인](#5-데이터-적재-파이프라인)
- [6. 요청 시퀀스](#6-요청-시퀀스)

---

## 1. 시스템 아키텍처

```mermaid
graph TB
  subgraph client[프론트엔드]
    UI["React Vite SPA<br/>카카오톡 챗 · 이미지 · 근거 · 메트릭 배지"]
  end

  subgraph backend[FastAPI 백엔드]
    M["main.py<br/>엔드포인트 · 캐시 · 로깅"]
    PIPE["pipeline.py<br/>RAG 조율 · 멀티턴 · 개인화 · 라우팅"]
    PB["prompt_builder.py<br/>프롬프트 · 가드레일"]
    VS["vector_store.py"]
    US["user_store.py"]
    RL["request_log.py"]
    LLM["llm_api.py · embeddings.py"]
    HAPI["heritage_api.py"]
  end

  subgraph ext[외부 서비스]
    G["Google Gemini API<br/>생성 + 임베딩"]
    KHS["국가유산청 Open API"]
  end

  subgraph db[PostgreSQL pgvector]
    T1[("heritage_chunks 벡터")]
    T2[("users · user_interests")]
    T3[("request_logs")]
  end

  UI --> M
  M --> PIPE
  M --> RL
  PIPE --> PB
  PIPE --> VS
  PIPE --> US
  PIPE --> LLM
  PIPE --> HAPI
  LLM --> G
  HAPI --> KHS
  VS --> T1
  US --> T2
  RL --> T3
```

> pgvector는 별도 DB가 아니라 **PostgreSQL의 확장**. 벡터·개인화·로그 테이블이 한 DB에 있다.

---

## 2. ERD (데이터 모델)

```mermaid
erDiagram
  USERS ||--o{ USER_INTERESTS : owns
  USERS ||..o{ REQUEST_LOGS : refs

  HERITAGE_CHUNKS {
    int id PK
    text source_type
    text heritage_name
    text term
    int chunk_index
    text content
    text image_url
    text category
    vector embedding
  }

  USERS {
    text id PK
    timestamp created_at
  }

  USER_INTERESTS {
    text user_id FK
    text category
    real weight
  }

  REQUEST_LOGS {
    int id PK
    timestamp ts
    text endpoint
    text question
    text user_id
    bool cached
    bool condensed
    bool multiturn
    text answer_model
    int total_tokens
    int latency_ms
    int num_sources
  }
```

> `source_type` 은 heritage / term / note. `category` 는 분류(bcodeName)로 개인화 가중치에 쓰인다.

---

## 3. RAG 질의 플로우 (`/api/rag`)

```mermaid
flowchart TD
  Q["질문 + 이력 + user_id"] --> CK{"단일턴 · 비개인화?"}
  CK -->|"캐시 HIT"| HIT["캐시 응답<br/>LLM 0회 · 즉시"]
  CK -->|"MISS"| GATE{"이력 있고 지시어 있나?"}

  GATE -->|"예"| RW["질의 재작성<br/>flash-lite"]
  GATE -->|"아니오"| KEEP["원 질문 사용"]

  RW --> EMB["질문 임베딩<br/>gemini-embedding-001"]
  KEEP --> EMB
  EMB --> HR["하이브리드 검색<br/>벡터 + 이름필터 + 키워드"]
  HR --> SUBJ["주제 유산 추리기<br/>곁다리 제외"]
  SUBJ --> ROUTE{"비교 또는 상위개념?"}
  ROUTE -->|"예"| FULL["생성: flash"]
  ROUTE -->|"아니오"| LITE["생성: flash-lite"]

  FULL --> GUARD["가드레일 + 관심사 + 맥락 주입"]
  LITE --> GUARD
  GUARD --> ANS["답변 + 이미지 + 근거"]
  ANS --> BUMP["관심 가중치 누적"]
  ANS --> LOG["토큰 지연 기록<br/>request_logs"]
  HIT --> LOG
```

---

## 4. 기본 해설 파이프라인 (`/api/heritage`)

```mermaid
flowchart LR
  N["유산 이름"] --> S1["1 목록 API<br/>식별자 추출"]
  S1 --> S2["2 상세 API<br/>content · imageUrl"]
  S2 --> S3["3 용어 레이어<br/>전문용어 탐지 · 정의 주입"]
  S3 --> S4["4 LLM 해설<br/>왜곡 없는 한국어"]
  S4 --> S5["5 번역<br/>en · zh · ja"]
  S5 --> OUT["해설 + 이미지 + 탐지용어"]
```

---

## 5. 데이터 적재 파이프라인

```mermaid
flowchart TD
  subgraph src[소스]
    HC["국가유산 원문"]
    TD["용어 사전"]
    KN["검증된 지식 메모"]
  end

  HC --> CHUNK["청크 분할<br/>문단 300자"]
  CHUNK --> EMB["임베딩 768차원"]
  TD --> EMB
  KN --> EMB
  EMB --> PG[("pgvector heritage_chunks")]
```

> 명령: `python ingest.py` · `--bulk 11 25` · `--notes` · `--backfill-categories`

---

## 6. 요청 시퀀스

```mermaid
sequenceDiagram
  autonumber
  participant U as 사용자
  participant A as FastAPI
  participant P as pipeline
  participant DB as PostgreSQL
  participant G as Gemini

  U->>A: POST /api/rag
  A->>DB: 관심사 조회 캐시 확인
  alt 캐시 HIT
    A-->>U: 캐시 응답 토큰 0
  else MISS
    A->>P: rag_answer
    opt 지시어 후속
      P->>G: 질의 재작성 flash-lite
    end
    P->>G: 질문 임베딩
    P->>DB: 하이브리드 검색
    P->>G: 응답 생성 가드레일 라우팅
    P->>DB: 관심 가중치 누적
    P-->>A: 답변 meta
  end
  A->>DB: request_logs 기록
  A-->>U: 답변 이미지 근거 meta
```

---

### 관련 문서
[RAG 원리](RAG.md) · [정확도 평가](EVAL.md) · [README](../README.md)
```
