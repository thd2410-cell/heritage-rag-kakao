# 로컬 실행 매뉴얼

> 순서: **① 인프라(Docker) → ② 백엔드 → ③ 프론트엔드**
> 예시는 Windows(Git Bash) 기준. PowerShell/mac/Linux는 각 단계의 메모 참고.

## 0. 사전 준비
- Python 3.11+ · Node.js 18+ · Docker Desktop(실행 중이어야 함)

---

## ① 인프라 — pgvector(PostgreSQL) 올리기

프로젝트 루트에서:
```bash
docker compose up -d          # heritage-pgvector 컨테이너 기동
docker ps                     # STATUS가 healthy 인지 확인
```
- 끄기: `docker compose down` (데이터 유지) / `docker compose down -v` (데이터 삭제)

---

## ② 백엔드 — venv · 의존성 · 적재 · 서버

### 2-1. 가상환경(venv) 생성·활성화
가상환경은 **프로젝트 루트의 `.venv`** 를 사용한다.
```bash
# 프로젝트 루트에서 (최초 1회)
python -m venv .venv

# 활성화
source .venv/Scripts/activate     # Windows(Git Bash)
# PowerShell:   .\.venv\Scripts\Activate.ps1
# mac/Linux:    source .venv/bin/activate
```
> 프롬프트 앞에 `(.venv)` 가 뜨면 활성화 성공. 끌 땐 `deactivate`.

### 2-2. 의존성 설치
```bash
pip install -r backend/requirements.txt
```

### 2-3. 환경변수(.env)
```bash
cp backend/.env.example backend/.env
# backend/.env 를 열어 GEMINI_API_KEY 입력 (필수)
```

### 2-4. 벡터 DB 적재 (최초 1회)
```bash
cd backend
python ingest.py                    # 초기화 + 용어 + 지식메모 + 기본 유산
python ingest.py --bulk 11 25       # (선택) 국보 25건 추가
python ingest.py --bulk 12 20       # (선택) 보물
python ingest.py --bulk 13 15       # (선택) 사적
python ingest.py --backfill-images       # (선택) 이미지 URL 채우기
python ingest.py --backfill-categories   # (선택) 분류 채우기
```

### 2-5. 서버 실행
```bash
# backend 디렉터리에서
uvicorn main:app --reload --port 8000
```
- 확인: 브라우저/curl `http://localhost:8000/` → `{"status":"ok", ...}`

---

## ③ 프론트엔드 — React(Vite)

새 터미널에서:
```bash
cd frontend
npm install                  # 최초 1회
npm run dev                  # http://localhost:5173 자동 오픈
```
- 백엔드(8000)가 떠 있어야 챗이 동작한다. CORS는 개방되어 있다.

---

## 한눈에 (요약)
```bash
# 1) 인프라
docker compose up -d

# 2) 백엔드
source .venv/Scripts/activate          # (최초: python -m venv .venv)
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env   # GEMINI_API_KEY 입력
cd backend && python ingest.py         # (최초 1회 적재)
uvicorn main:app --reload --port 8000

# 3) 프론트엔드 (새 터미널)
cd frontend && npm install && npm run dev
```

## 자주 겪는 문제
- **포트 8000 WinError 10013** → 이미 사용 중. 기존 프로세스 종료 또는 `--port 8001`.
- **DB 연결 실패** → `docker ps` 로 pgvector healthy 확인, `docker compose up -d` 재실행.
- **404 (모델)** → `.env`의 모델명 확인: 채팅 `gemini-2.5-flash`, 임베딩 `gemini-embedding-001`.
- **국가유산청 API 간헐 실패(WinError 10061)** → 외부 서버 불안정. ingest 재실행 시 중복 제외하고 빠진 것만 채움.
