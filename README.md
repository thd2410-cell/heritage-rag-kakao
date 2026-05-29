# 국가유산 AI 해설 챗봇 MK0

맥미니에서 실행하는 **국가유산청 Open API + PostgreSQL/pgvector + FastAPI + Kakao Skill Webhook** 기반 RAG 챗봇 MVP입니다.

## 현재 MK0 포함 범위

- 국가유산 목록/상세 Open API 수집 스크립트
- 서울/경북 + 국보/보물/사적 우선 수집 기본값
- PostgreSQL + pgvector 테이블
- `BAAI/bge-m3` 임베딩
- RAG Top 3 검색
- 도메인 제한 정책
- FastAPI `/api/rag/ask`
- Kakao Skill Webhook `/api/kakao/skill`
- 쉬운 설명/심화 설명/퀴즈/관련 유산 quickReplies

## 제외 범위

AR, 이미지 인식, GPS 인증, 다국어, 게임화, 지도, 로그인, 관리자 페이지.

## 구조

```txt
heritage-rag-kakao/
  backend/
    app/
      api/
      core/
      db/
      models/
      schemas/
      services/
    db/init.sql
    Dockerfile
    requirements.txt
  scripts/collect_heritages.py
  data/
  docker-compose.yml
  .env.example
  README.md
```

## 실행 준비

```bash
cp .env.example .env
```

LLM 답변 생성을 쓰려면 `.env`에 `OPENAI_API_KEY`를 넣어야 합니다.  
키가 없으면 검색 파이프라인 확인용 임시 답변만 반환합니다.

## DB/API 실행

```bash
docker compose up --build
```

상태 확인:

```bash
curl http://localhost:8000/health
```

## 초기 데이터 수집

Docker DB가 실행 중인 상태에서, 로컬 Python 또는 API 컨테이너 안에서 실행합니다.

로컬 실행 예시:

```bash
cd heritage-rag-kakao
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
python scripts/collect_heritages.py --limit 50
```

임베딩 모델 다운로드가 부담되면 먼저 구조 확인만 할 수 있습니다.

```bash
python scripts/collect_heritages.py --limit 10 --no-embed
```

단, `--no-embed` 데이터는 RAG 검색에는 사용되지 않습니다.

## RAG 테스트

```bash
curl -X POST http://localhost:8000/api/rag/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"경복궁 쉽게 설명해줘"}'
```

## Kakao Skill Webhook

Skill URL:

```txt
POST https://<공개 HTTPS URL>/api/kakao/skill
```

Kakao 요청에서 사용:

- `userRequest.utterance`
- `userRequest.user.id`

응답:

- `simpleText`
- quickReplies: 쉽게 설명 / 심화 설명 / 퀴즈 / 관련 유산

## 도메인 제한 정책

국가유산 관련 질문이 아니면 항상 아래 문구를 반환합니다.

```txt
저는 국가유산 전문 AI 해설사입니다.
국가유산, 문화재, 유적, 유물과 관련된 질문을 부탁드립니다.
```

## 인프라 / CI-CD

1번 구조로 **맥미니 단일 서버 + Docker Compose + GitHub Actions self-hosted runner** 구성을 추가했습니다.

자세한 내용은 `docs/INFRA.md`를 확인하세요.

```bash
cp .env.production.example .env.production
./scripts/deploy.sh
```

## 다음에 사용자 확인이 필요한 단계

지시서에 따라 아래는 임의로 진행하지 않습니다.

- OpenAI API Key 입력
- Kakao 채널/Skill 생성 및 URL 등록
- ngrok 또는 Cloudflare Tunnel 설치/설정
- Docker/pgvector 설치 문제 발생 시 조치 선택
- Open API 응답 구조 변경/호출 실패 대응
- 초기 수집 범위 변경
