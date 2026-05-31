# Heritage Chat Frontend

React + Vite 기반 국가유산 AI 해설 챗봇 프론트엔드입니다.

## Local development

```bash
npm ci
npm run dev
```

개발 서버는 `/api/*` 요청을 `http://127.0.0.1:8000` 백엔드로 프록시합니다.

## Production

프로덕션은 Docker 멀티 스테이지 빌드로 정적 파일을 만들고 nginx가 서빙합니다.
nginx는 `/api/*`를 Docker Compose 내부의 `api:8000`으로 프록시합니다.

```bash
docker build . -t heritage-rag-kakao-frontend:local
```

## Environment

기본은 same-origin API 사용입니다. API가 다른 도메인에 있을 때만 설정합니다.

```bash
VITE_API_BASE_URL=https://example.com
```
