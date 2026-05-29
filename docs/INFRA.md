# 인프라 / CI-CD 운영 메모

## 선택한 1번 구조

맥미니 단일 서버에서 Docker Compose로 운영합니다.

```txt
GitHub main push
  -> GitHub Actions CI
  -> self-hosted runner on Mac mini
  -> scripts/deploy.sh
  -> docker compose -f docker-compose.prod.yml up -d --build
  -> FastAPI + PostgreSQL/pgvector
```

이 방식은 SSH 배포보다 단순합니다. 맥미니가 직접 GitHub Actions runner로 동작하므로 외부에서 맥미니 SSH 포트를 열 필요가 없습니다.

## 파일

- `docker-compose.yml`: 로컬 개발용
- `docker-compose.prod.yml`: 운영용
- `.env.production.example`: 운영 환경변수 예시
- `scripts/deploy.sh`: 운영 배포
- `scripts/backup_db.sh`: DB 백업
- `.github/workflows/ci.yml`: 문법/Compose/Docker build 검증
- `.github/workflows/deploy.yml`: main push 또는 수동 실행 시 맥미니 배포

## 맥미니 최초 준비 체크리스트

1. Docker Desktop 실행
2. GitHub 저장소 생성/푸시
3. GitHub self-hosted runner 설치
   - labels: `self-hosted`, `macOS`, `heritage-rag`
4. 서버 작업 디렉터리에 `.env.production` 생성
5. `POSTGRES_PASSWORD`를 긴 랜덤 값으로 교체
6. 필요 시 `OPENAI_API_KEY` 입력
7. `./scripts/deploy.sh`로 첫 배포

## 운영 포트 정책

기본값은 외부 직접 노출을 막기 위해 로컬 바인딩입니다.

- API: `127.0.0.1:8000`
- PostgreSQL: `127.0.0.1:5432`

카카오 Skill 연결 단계에서 HTTPS URL이 필요하면 그때 ngrok 또는 Cloudflare Tunnel을 선택합니다.

## 배포

```bash
cp .env.production.example .env.production
# .env.production 수정
./scripts/deploy.sh
```

상태 확인:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production ps
curl http://127.0.0.1:8000/health
```

## 백업

```bash
./scripts/backup_db.sh
```

백업 파일은 `data/backups/*.dump`에 생성됩니다.

## 현재 멈춰야 하는 지점

다음은 사용자 확인 후 진행합니다.

- Docker Desktop 실행/설치 문제
- GitHub 저장소 생성 위치
- GitHub self-hosted runner 등록
- `.env.production` 실제 비밀번호/API 키 입력
- ngrok vs Cloudflare Tunnel 선택
