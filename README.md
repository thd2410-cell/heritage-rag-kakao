# 국가유산 AI 해설사 🏛️

국가유산청 Open API + LLM + RAG(pgvector) 기반 다국어 국가유산 해설 챗봇.
어떤 질문에도 **원문에 근거해 왜곡 없이** 한국어 해설과 다국어 번역을 제공하고,
**검색된 자료에 없는 내용은 "확인되지 않습니다"** 로 답하며 **잘못된 전제는 정정**한다.

> SSAFY × Kakao 해커톤 — 정부 선정 AI 민생 10대 프로젝트 "국가유산 AI 해설사" 구현.

---

## 📚 문서

| 문서 | 내용 |
|---|---|
| **[로컬 실행 매뉴얼](docs/LOCAL_SETUP.md)** | Docker · 백엔드(venv) · 프론트 실행 — 처음이면 여기부터 |
| [시스템 정리 문서](docs/PROJECT_SUMMARY.md) | 개요 · 구성요소 · 구현 현황 (보고서용) |
| [아키텍처 · 다이어그램](docs/ARCHITECTURE.md) | Mermaid: 시스템·ERD·RAG 플로우·시퀀스 |
| [RAG 원리와 적용](docs/RAG.md) | RAG 4단계가 우리 코드 어디에 있는지 |
| [정확도 평가](docs/EVAL.md) | 정답지·하이브리드 채점·정직한 벤치마크 |

---

## 목차
- [주요 기능](#주요-기능)
- [기술 스택](#기술-스택)
- [아키텍처](#아키텍처)
- [파일 구조](#파일-구조)
- [설치 및 실행](#설치-및-실행)
- [환경변수](#환경변수)
- [API 엔드포인트](#api-엔드포인트)
- [핵심 구현](#핵심-구현)
- [개발 진행 기록](#개발-진행-기록)
- [알려진 제약](#알려진-제약)

---

## 주요 기능

| 기능 | 설명 |
|---|---|
| **유산 해설** | 유산 이름 → 국가유산청 API 조회 → LLM이 원문 기반 자연스러운 해설 생성 |
| **다국어 번역** | 한국어 해설을 영어·중국어·일본어로 번역 (고유명사 원어 병기) |
| **용어 사전 레이어** | 전문 용어(홍예문·우진각지붕 등) 자동 탐지 후 정의를 LLM에 주입 → 왜곡 방지 |
| **용어 자동 확장** | `단어(한자)` 패턴 추출 → LLM이 정의 생성 → 사전 자동 등록 (고유명사 SKIP) |
| **RAG 질의응답** | 질문 임베딩 → pgvector 코사인 검색 → 상위 청크만 근거로 답변 |
| **하이브리드 검색** | 벡터(의미) + 유산명 필터(균형) + 키워드(ILIKE) 결합 |
| **환각 방지** | 자료에 없으면 "확인되지 않습니다", 잘못된 전제는 정정 |
| **멀티턴 대화** | "그 둘 중 더 오래된 건?" 같은 지시어를 이전 맥락으로 해석(질의 재작성) |
| **이미지 의도 게이트** | "보여줘/소개"엔 사진, "폭설로 무너졌어?" 같은 사실 질문엔 답만 |
| **개인화(관심사 자동학습)** | 검색된 유산 분류로 관심 가중치 누적 → 답변을 관심 분야 쪽으로 |
| **관심사 기반 추천** | 학습된 관심 분야의 유산을 추천 칩으로 제시 |
| **카카오톡 스타일 챗 UI** | 이미지 표시 · 근거 원문 펼쳐보기 · 마크다운 · 4개 국어 |
| **응답 캐싱 + 모델 라우팅** | 단일턴 캐시 + 단순 질문은 저렴 모델로 비용 절감 |

---

## 기술 스택

- **백엔드**: Python 3.11 · FastAPI · uvicorn
- **LLM**: Google Gemini (`gemini-2.5-flash`) — provider 추상화로 OpenAI 교체 가능
- **임베딩**: Gemini `gemini-embedding-001` (768차원) — OpenAI `text-embedding-3-small` 교체 가능
- **벡터 DB**: PostgreSQL + pgvector — pgvector는 별도 DB가 아니라 **PostgreSQL 확장(extension)**. 컨테이너 1개에 벡터·개인화·로그 테이블이 모두 한 DB에 있다.
- **데이터**: 국가유산청 Open API (XML)
- **프론트엔드**: React 18 · Vite (SPA) · react-markdown
- **언어**: 한국어 · 영어 · 중국어 · 일본어

---

## 아키텍처

> 📊 **Mermaid 다이어그램**(시스템 아키텍처 · ERD · RAG 플로우 · 시퀀스): **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**

### 기본 해설 파이프라인 (`/api/heritage`)
```
유산 이름
  ↓ 1. 목록 API → 유산 식별 (ccbaKdcd/ccbaAsno/ccbaCtcd)
  ↓ 2. 상세 API → content(원문), imageUrl
  ↓ 3. 용어 레이어 → 전문 용어 탐지 + [용어 정의] 컨텍스트 주입
  ↓ 4. LLM → 왜곡 없는 한국어 해설
  ↓ 5. LLM → 다국어 번역
응답: 해설 + 이미지 + 탐지 용어 (+ 캐싱)
```

### RAG 파이프라인 (`/api/rag`)
```
사용자 질문
  ↓ 질문 임베딩 (gemini-embedding-001, 768차원)
  ↓ 하이브리드 검색
  │    ├─ 이름 필터: 질문에 언급된 유산별 균형 검색
  │    ├─ 전역 벡터: 코사인 유사도 top-k
  │    └─ 키워드: ILIKE 보강
  ↓ 검색된 청크만 LLM 컨텍스트로 주입 (grounded)
응답: 답변 + 대표 이미지 + 근거 청크(출처/유사도)
```

### 데이터 적재 (`ingest.py`)
```
국가유산 원문 ──┐
              ├─ 문단 기준 300자 청크 분할 ─→ 임베딩 ─→ pgvector(heritage_chunks)
용어 사전 ─────┘
```

---

## 파일 구조

```
heri-chat-bot/
├── docker-compose.yml          # PostgreSQL + pgvector
├── CLAUDE.md                   # 원본 기획/명세
├── README.md                   # (이 문서)
│
├── backend/
│   ├── main.py                 # FastAPI 앱 · 엔드포인트 · CORS · 캐시
│   ├── ingest.py               # 원문/용어 청크·임베딩 적재 (+ bulk/backfill/notes)
│   ├── eval/                   # 정확도 평가 (eval_set.json · run_eval.py · gen_eval.py)
│   ├── requirements.txt
│   ├── .env / .env.example     # API 키 · 모델 · DB 설정
│   ├── api/
│   │   ├── heritage_api.py     # 국가유산청 API (목록/상세, XML 파싱, 재시도)
│   │   ├── llm_api.py          # LLM 호출 추상화 (Gemini/OpenAI)
│   │   └── embeddings.py       # 임베딩 추상화 (Gemini/OpenAI)
│   ├── core/
│   │   ├── pipeline.py         # 전체 파이프라인 조율 + RAG + 후속질문
│   │   ├── term_extractor.py   # 용어 탐지·추출·사전 확장
│   │   ├── prompt_builder.py   # 해설/번역/RAG/후속질문 프롬프트 조립
│   │   ├── chunker.py          # 문단 기준 청크 분할
│   │   ├── vector_store.py     # pgvector 스키마/저장/검색 (+ 분류·추천 쿼리)
│   │   ├── user_store.py       # 사용자 관심사 가중치 (개인화)
│   │   ├── request_log.py      # 요청별 토큰·지연 로그 + 집계 (관측성)
│   │   └── cache.py            # LRU + TTL 인메모리 캐시
│   └── data/
│       └── term_dictionary.json # 용어 사전 (시드 + 자동 확장)
│
└── frontend/
    ├── index.html              # Vite 진입점
    ├── vite.config.js
    ├── package.json
    ├── standalone.html         # (구) CDN 단일파일 풀기능 UI 백업
    └── src/
        ├── main.jsx
        ├── App.jsx             # 카카오톡 스타일 RAG 챗봇
        └── index.css
```

---

## 설치 및 실행

### 1. 사전 준비
- Python 3.11+, Node.js 18+, Docker Desktop

### 2. 벡터 DB (pgvector) 기동
```bash
docker compose up -d
```

### 3. 백엔드
```bash
cd backend
python -m venv .venv          # 최초 1회 (프로젝트 루트에 .venv 사용)
# Windows(Git Bash): source ../.venv/Scripts/activate
# macOS/Linux:        source ../.venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # API 키 입력 (GEMINI_API_KEY)

# 벡터 DB 적재 (최초 1회: 초기화 + 용어 + 기본 유산)
python ingest.py
python ingest.py --bulk 11 25       # 국보 25건 추가
python ingest.py --bulk 12 20       # 보물 20건 추가
python ingest.py --bulk 13 15       # 사적 15건 추가
python ingest.py --backfill-images  # 이미지 URL 백필

# 서버 실행
uvicorn main:app --reload --port 8000
```

### 4. 프론트엔드
```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173 자동 오픈
```

---

## 환경변수

`backend/.env`:

```ini
# LLM provider: "gemini" 또는 "openai"
LLM_PROVIDER=gemini
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.5-flash
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1

# 임베딩 (기본은 LLM_PROVIDER 따름)
EMBED_PROVIDER=gemini
GEMINI_EMBED_MODEL=gemini-embedding-001
GEMINI_EMBED_DIM=768
OPENAI_EMBED_MODEL=text-embedding-3-small

# pgvector (docker-compose)
PGHOST=localhost
PGPORT=5432
PGUSER=heritage
PGPASSWORD=heritage
PGDATABASE=heritage
```

`frontend/.env` (선택): `VITE_API_BASE=http://localhost:8000`

> ⚠️ 이 프로젝트의 Gemini 키는 일부 모델만 지원한다. 채팅은 `gemini-2.5-flash`,
> 임베딩은 `gemini-embedding-001` 을 써야 한다. (`gemini-2.0-flash`, `text-embedding-004` 는 404)

---

## API 엔드포인트

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/` | 헬스 체크 + LLM 설정 + 캐시 통계 |
| GET | `/api/heritage?name=숭례문&lang=ko` | 유산 해설/번역 (lang: ko/en/zh/ja) |
| POST | `/api/rag` | RAG 질의응답 (`{question, lang, top_k, history, user_id}`) |
| GET | `/api/me?user_id=` | 사용자의 학습된 관심 분야(가중치) |
| GET | `/api/recommend?user_id=&n=3` | 관심 분야 기반 유산 추천 |
| GET | `/api/metrics` | 정량 평가 집계 (캐시 적중률·모델별 평균 토큰/지연) |
| POST | `/api/ask` | 단일 유산 grounding 후속 질문 (`{name, content, question, ...}`) |
| POST | `/api/expand-terms` | 원문에서 신규 용어 자동 등록 (`{content}`) |

### `/api/heritage` 응답 예
```json
{
  "name": "서울 숭례문",
  "hanja": "서울 崇禮門",
  "period": "조선 태조 7년(1398)",
  "imageUrl": "http://www.khs.go.kr/.../2685609.jpg",
  "explanation": "조선시대 한양도성의 정문으로...",
  "lang": "ko",
  "detected_terms": ["석축", "홍예문", "우진각지붕", "다포 양식", ...],
  "content": "...(grounding 원문)...",
  "cached": false
}
```

### `/api/rag` 응답 예
```json
{
  "answer": "아닙니다, 숭례문은 폭설로 무너진 적이 없습니다. 2008년 방화 화재로...",
  "lang": "ko",
  "imageUrl": "http://www.khs.go.kr/.../2685609.jpg",
  "imageName": "서울 숭례문",
  "sources": [
    { "label": "서울 숭례문", "similarity": 0.7252, "snippet": "...", "content": "...(근거 원문 전체)..." }
  ]
}
```

---

## 핵심 구현

### 용어 사전 레이어 (왜곡 방지의 핵심)
- `content`에서 사전 등록 용어를 탐지(긴 용어 우선: "다포 양식" > "다포")
- 탐지된 용어 정의를 `[용어 정의]` 블록으로 LLM 시스템 프롬프트에 주입
- 정규식 `([가-힣]+)(한자)` 로 신규 용어 후보 자동 추출 → LLM 정의 생성 → 사전 확장
  - 고유명사(사건명/인물명 등)는 LLM이 `SKIP` 판정해 제외

### 하이브리드 검색 (비교 질문 대응)
순수 벡터 검색은 유사도 높은 한쪽 유산에 쏠릴 수 있어, 세 신호를 결합:
1. **이름 필터** — 질문에 언급된 유산을 감지해 유산별로 균형 있게 검색
2. **전역 벡터** — 코사인 유사도 상위 청크
3. **키워드** — ILIKE 보강
→ content 중복 제거 후 우선순위 병합. "A랑 B 비교해줘" 류에서 양쪽 청크 모두 확보.

### LLM/임베딩 provider 추상화
`call_llm()` / `embed_texts()` 단일 진입점 + 환경변수 한 줄로 Gemini ↔ OpenAI 교체.
SDK 의존성 없이 REST 호출, 429/연결오류 지수 백오프 재시도.

### 멀티턴 대화 (질의 재작성)
후속 질문에 지시어("그 둘", "거기", "더")가 있으면, 이전 대화로 **독립 검색어로 재작성**(condense)한 뒤 검색한다. 유산명을 직접 말한 자족적 후속은 재작성을 건너뛴다.

### 이미지 표시 = 질문 의도
"숭례문/남대문/설명해줘/A랑 B 비교"처럼 **보여줄 의도**일 때만 사진을 띄우고, "폭설로 무너졌어?" 같은 **특정 사실 질문**엔 답만 준다. "원각사"처럼 코퍼스에 없는 **상위 개념**은 사진을 보류하고 개별 유산(십층석탑 등)을 제안한다.

### 개인화 (관심사 자동학습)
익명 `user_id`(localStorage) 기준으로, 검색된 유산의 분류(bcodeName: 종교신앙·정치국방 등)를 `user_interests` 가중치로 누적한다. 로그인·LLM 분류 없이 학습되며, 상위 관심 분야를 생성 프롬프트에 주입해 답변을 그 측면으로 살짝 기울인다. `/api/recommend`로 관심 분야 유산을 추천한다.

### 비용 최적화
- **응답 캐싱**: `/api/heritage`는 `name|lang`, `/api/rag`는 단일턴·비개인화 질문을 `lang|question`으로 LRU+TTL 캐싱 (용어 확장 시 무효화).
- **모델 라우팅**: 비교·상위개념은 `gemini-2.5-flash`, 단순 단일 질문·질의 재작성은 저렴한 `gemini-2.5-flash-lite`.
- **condense 게이팅**: 지시어가 있는 후속만 재작성 호출 → 대부분의 후속에서 LLM 호출 1회 절약.
- **이력 다이어트**: 최근 4턴·발화당 160자로 잘라 입력 토큰 축소.

### 정확도 평가 (Evaluation)
정답지(gold set)와 챗봇 답변을 **유형별 하이브리드 채점**(키워드/거부/LLM심판)으로 비교해 카테고리별·전체 정확도를 낸다. 함정·멀티홉 문항으로 변별력을 확보하고, 대량 생성(LLM 초안→사람 검수)으로 셋을 키운다. → 방법론·실행법은 **[docs/EVAL.md](docs/EVAL.md)**.
```bash
cd backend && python eval/run_eval.py        # 정확도 산출
python eval/gen_eval.py 15 3                  # 정답지 초안 대량 생성(검수 필요)
```

### 관측성 (정량 평가)
정성적인 가드레일과 달리 "얼마나 좋아졌는지"를 숫자로 증명하기 위해 요청별 메트릭을 기록한다.
- 버려지던 LLM 응답의 `usageMetadata`(Gemini)·`usage`(OpenAI)에서 **토큰 수를 포착**하고, `Meter`로 condense+generate 호출을 합산.
- 요청별 **토큰·지연·캐시여부·사용모델·condense여부**를 `request_logs` 테이블(같은 PostgreSQL)에 기록.
- 응답에 `meta`(즉시 확인), 챗 말풍선에 **⚡ 지연·토큰·모델 배지**, `GET /api/metrics`로 집계.
- 측정 예: 캐시 적중 = 0토큰·즉시 / 단순질문 `flash-lite` ≈ 1.9s / 비교 `flash` ≈ 8s → 라우팅·캐시 효과를 정량 입증.

---

## 개발 진행 기록

| 단계 | 내용 |
|---|---|
| **Phase 1 MVP** | 국가유산청 API 모듈 → 용어 사전 레이어 → LLM 해설 → 영어 번역 → FastAPI → React UI |
| **Phase 2** | 후속 질문(대화 맥락) · 용어 사전 자동 확장 · 응답 캐싱 |
| **RAG 업그레이드** | docker-compose(pgvector) · 청크 분할 · 임베딩 · 벡터 저장/검색 · RAG 파이프라인 |
| **UI 개편** | 카카오톡 스타일 채팅 SPA · 마크다운 · 다국어 |
| **확장** | 유산 대량 적재(54종/366청크) · 하이브리드 검색 · 답변 이미지 · 근거 원문 펼쳐보기 |

### 검증된 시나리오
- ✅ "숭례문은 폭설로 무너진 적 있어?" → 방화 청크 검색 → **잘못된 전제 정정**
- ✅ "숭례문이랑 원각사지 십층석탑 비교해줘" → **두 유산 청크 동시 검색**
- ✅ "숭례문(국보)이랑 수원 화성(사적) 비교해줘" → **교차 종목 비교**
- ✅ "경복궁 근정전 높이?" (미적재) → **"확인되지 않습니다"**

---

## 알려진 제약

- **국가유산청 API가 간헐적으로 연결을 거부**한다(WinError 10061). 재시도 로직으로 완화하지만
  bulk 적재 시 일부 유산이 누락될 수 있다. → `python ingest.py --bulk 12 30` 재실행하면
  중복을 제외하고 빠진 것만 채운다.
- **Gemini 무료 티어 레이트리밋(429)** — 테스트 호출이 많으면 발생. 임베딩 호출은 백오프 재시도로 보호.
- 현재 RAG 코퍼스는 국보/보물/사적 일부(54종)만 적재. `--bulk`로 확장 가능.
- 벡터 차원(768)은 임베딩 provider에 종속 — provider 교체 시 재적재 필요.
```
