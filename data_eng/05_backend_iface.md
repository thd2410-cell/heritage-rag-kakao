# 박스 05 — 팀 백엔드 인터페이스 ⭐ 미해결 핵심

## 목적
BK의 데이터 엔지니어링 결과를 팀 백엔드(`heritage-rag-kakao`)에 통합한다.

## 현재 상태
⬜ 미해결 — **가장 큰 의사결정 필요. 본선 통합 때 터질 수 있는 가장 큰 리스크.**

---

## 갭 분석 — BK 실험 vs 팀 운영

| 영역 | BK 실험 (`kakao/trial/rag/`) | 팀 백엔드 (`heritage-rag-kakao/`) |
|---|---|---|
| **임베딩 모델** | KoSimCSE-roberta | **BAAI/bge-m3** |
| **벡터 DB** | ChromaDB | **PostgreSQL + pgvector** |
| **정제 코드 위치** | `fetcher.py` 안에 내장 | `backend/app/services/chunking.py` |
| **인덱서** | `practice/rag/indexer.py` | `scripts/collect_heritages.py` |
| **데이터 스키마** | `heritages.json` (단일 파일) | PostgreSQL 테이블 (`backend/db/init.sql`) |
| **답변 LLM** | gpt-4o-mini | gpt-4o-mini (+ Ollama 옵션) |
| **운영 환경** | 로컬 Python | Docker Compose + 맥미니 + GitHub Actions |

---

## 결정해야 할 것 4가지

### ① 임베딩: KoSimCSE → bge-m3 전환?

- KoSimCSE 실험 결과 70.6% (Exp-102) — bge-m3로 옮기면 결과 모름
- bge-m3 임베딩 차원 ≠ KoSimCSE → 재인덱싱 필요
- **결정 필요**: bge-m3 1라운드 평가 → KoSimCSE보다 나으면 전환 / 나쁘면 운영용 KoSimCSE 사용 가능성?

### ② 벡터 DB: ChromaDB → pgvector 이관

- heritages.json → PostgreSQL 테이블 insert + embedding 컬럼 생성
- 두 가지 길:
  - (a) BK가 직접 SQL insert 스크립트 작성
  - (b) 팀 `scripts/collect_heritages.py`에 BK 정제 결과(JSON) 넘기고 팀이 인덱싱

### ③ 정제 코드 위치

- (a) BK 정제 룰을 팀 `backend/app/services/chunking.py`에 PR로 반영
- (b) BK가 정제 결과(JSON)만 넘기고 팀이 인덱싱 통합

→ **(b)가 작업 부담 적음** (BK 정제 결과만 transfer, 팀 코드 수정 최소)

### ④ 작업 위치

- (a) BK 작업 폴더 `kakao/trial/rag/`에서 통합 코드 작성
- (b) 팀 레포 `heritage-rag-kakao/` PR 브랜치에서 작성

→ **(b)가 맞음.** 통합 단계 = 팀 레포 PR.

---

## BK 잠정 결정 (아직 미확정)

```
임베딩  bge-m3로 전환 후 1라운드 평가 → 본선 결정
        (단, 일정상 안 되면 KoSimCSE 운영 가능성도 열어둠)

벡터 DB pgvector로 통일 (운영 환경 일관성)

정제    BK는 (a) 정제 결과 JSON + (b) 정제 룰 문서를 팀에 전달
        → 팀이 인덱싱 통합 (BK 코드 PR은 최소)

작업    통합 단계는 팀 레포 PR 브랜치 (heritage-rag-kakao/)
        지금 단계는 kakao/trial/rag/ (문서·계획)
```

---

## 다음 액션 (BK)

```
1. [../data_schema.md](../data_schema.md) 8개 결정 확정 → 팀에 공유
2. heritages.json 627개 + 보물·시도 추가본 정제 완료
3. bge-m3 1라운드 평가 (KoSimCSE 결과와 비교) — Sprint 1 6/5~6/12
4. 팀과 통합 회의 — 위 4개 결정 합의
5. 팀 레포 PR 브랜치에서 통합 작업 (heritage-rag-kakao/)
```

---

## 미해결

- bge-m3 1라운드 평가 일정 (재인덱싱 시간이 Sprint 1 안에 맞나?)
- bge-m3가 KoSimCSE보다 나쁠 경우 대응
- 정제 룰 중 PostgreSQL 스키마 변경 요구하는 항목 (예: `name_hanja` 별도 필드)
- 팀 백엔드의 데이터 갱신 흐름(scripts/collect_heritages.py)과 BK 정제 결과의 결합 지점

---

## 참고

- 팀 백엔드: `../../../heritage-rag-kakao/backend/`
- 팀 README: `../../../heritage-rag-kakao/README.md`
- 팀 DB 스키마: `../../../heritage-rag-kakao/backend/db/init.sql`
- 팀 임베딩 서비스: `../../../heritage-rag-kakao/backend/app/services/embedding.py`
- BK 인덱서: `../practice/rag/indexer.py`
- BK 검색기: `../practice/rag/retriever.py`
