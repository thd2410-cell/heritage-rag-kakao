# RAG 데이터 수집 API 정리
## 역사톡 AI — 실제로 호출해서 쓸 국가유산 API 모음

> 목적: RAG에 넣을 국가유산 데이터를 어디서 어떻게 가져올지 정리
> 작업 위치: `trial/rag/practice/`
> 갱신: 2026-05-30

---

## 🎯 핵심 결론 (먼저 보기)

```
대부분 인증키 없이 URL 호출만으로 사용 가능 ✅
포맷은 거의 다 XML → Python에서 파싱 필요
서버에서 호출 (브라우저 직접 호출은 CORS 막힘)
```

---

## 1. ⭐ 국가유산청 통합 OPEN API (인증 불필요)

### 📋 사용 가능한 API 한눈에

| 종류 | URL | 용도 |
|------|-----|------|
| 국가유산검색 목록 | `http://www.khs.go.kr/cha/SearchKindOpenapiList.do` | 유산 목록 가져오기 |
| 국가유산검색 상세 | `http://www.khs.go.kr/cha/SearchKindOpenapiDt.do` | 특정 유산 상세 |
| 국가유산 이미지검색 | `http://www.khs.go.kr/cha/SearchImageOpenapi.do` | 유산 이미지 URL |
| 국가유산 동영상검색 | `http://www.khs.go.kr/cha/SearchVideoOpenapi.do` | 유산 동영상 URL |
| 국가유산 나레이션검색 | `http://www.khs.go.kr/cha/SearchVoiceOpenapi.do` | 음성 해설 (사회적 약자 대응용) |
| 국가유산 위치정보 | `http://www.gis-heritage.go.kr/openapi/xmlService/spca.do` | 좌표·지도용 |
| 국가유산 행사목록 | `http://www.khs.go.kr/cha/openapi/selectEventListOpenapi.do` | 유산 관련 행사 |

**가이드 페이지**: https://www.khs.go.kr/html/HtmlPage.do?mn=NS_04_04_03&pg=%2Fpublicinfo%2Fpbinfo3_0201.jsp

### 주요 파라미터 (공통)

| 파라미터 | 의미 | 예시 |
|---------|------|------|
| `ccbaKdcd` | 종목코드 | `11` (국보), `12` (보물), `13` (사적) |
| `ccbaAsno` | 관리번호 | `00000300` |
| `ccbaCtcd` | 시도코드 | `11` (서울) |

### 호출 예시

**A. 서울 지역 국보 목록**
```
http://www.khs.go.kr/cha/SearchKindOpenapiList.do?ccbaKdcd=11&ccbaCtcd=11
```

**B. 특정 유산 상세 (숭례문)**
```
http://www.khs.go.kr/cha/SearchKindOpenapiDt.do?ccbaKdcd=11&ccbaAsno=0000010000&ccbaCtcd=11
```

**C. 유산 이미지 목록**
```
http://www.khs.go.kr/cha/SearchImageOpenapi.do?ccbaKdcd=11&ccbaAsno=0000030000&ccbaCtcd=11
```

**D. 행사 목록 (월별)**
```
http://www.khs.go.kr/cha/openapi/selectEventListOpenapi.do?searchYear=2026&searchMonth=06
```

---

## 2. ⭐ 국가유산청 4대궁·종묘 상세 (인증 불필요)

> 정부 사업계획서 1차년도 타겟과 동일 → 발표 시 어필 포인트

**가이드**: https://www.data.go.kr/data/15028101/openapi.do
**참고 페이지**: http://www.cha.go.kr/html/HtmlPage.do?pg=/publicinfo/pbinfo3_0301.jsp

### API URL

**목록**
```
https://www.heritage.go.kr/heri/gungDetail/gogungListOpenApi.do?gung_number=1
```

**상세**
```
https://www.heritage.go.kr/heri/gungDetail/gogungDetailOpenApi.do?serial_number=0&detail_code=0&gung_number=1
```

### gung_number 값
- 1: 경복궁
- 2: 창덕궁
- 3: 창경궁
- 4: 덕수궁
- 5: 종묘 (확인 필요)

---

## 3. 보조 데이터 API

### A. 전국 지정문화재 현황 (data.go.kr)
- **페이지**: https://www.data.go.kr/data/15034324/openapi.do
- **URL**: http://www.cha.go.kr/html/HtmlPage.do?pg=/publicinfo/pbinfo3_0201.jsp&mn=NS_04_04_02
- **제공**: 문화재명, 지정일, 소재시도, 설명내용, 사진, 동영상, 음성파일
- **타입**: LINK (인증 불필요)
- **활용**: 전국 범위 텍스트 데이터

### B. 국가유산청 문화재 안내판 정보
- **페이지**: https://www.data.go.kr/data/15116563/fileData.do
- **타입**: 파일 데이터 (CSV/Excel 다운로드)
- **활용**: 현장 안내판 해설 텍스트 그대로 활용

### C. 전국향토문화유적표준데이터
- **페이지**: https://www.data.go.kr/data/15021147/standard.do
- **타입**: 표준데이터 (CSV)
- **활용**: 향토·지역 유적 보완

### D. 국가유산청 문화재 공간 정보 (지도용)
- **페이지**: https://www.data.go.kr/data/3070426/openapi.do
- **활용**: 카카오맵 코스 플래너 (P1)
- **타입**: XML

### E. 국가유산청 공공데이터 현황 (전체 목록)
- **URL**: https://www.khs.go.kr/html/HtmlPage.do?pg=/publicinfo/pbinfo2.jsp&mn=NS_04_04_01
- **활용**: 추가 API 탐색 시 참조

---

> ⚠️ **이하 F~H는 인증/다운로드 필요** — 위 A~E와 달리 서비스키 발급 또는 파일 다운로드 한 단계 더 거침. 절차는 표준 (data.go.kr 회원가입 → 자동 승인).

### F. e뮤지엄 유물정보 OpenAPI ⭐⭐⭐ 박물관 통합 (서비스키 필요)
- **신청 페이지**: https://www.data.go.kr/data/15104964/openapi.do
- **호출 엔드포인트**: `https://api.kcisa.kr/openapi/service/rest/meta/MPKreli`
  - 한국문화정보원(KCISA) 게이트웨이 경유. 도메인은 e뮤지엄과 달라 보이지만 정상.
- **인증**: 서비스키 (신청 후 이메일 발급, 개발 1,000회/일)
- **데이터**: 354개 박물관 약 250만 점 유물
- **호출 예시**: `{엔드포인트}?serviceKey={발급키}&numOfRows=10&pageNo=1`
- **샘플 코드**: 공공데이터포털에서 Python·Curl 등 제공
- **활용**: 챗봇 "심화 설명" + 웹앱 도감 (국보·보물·유물 단위 디테일)

### G. 한국역대인물 종합정보 데이터셋 ⭐⭐⭐ 인물 질문 (XML 파일)
- **다운로드**: https://www.data.go.kr/data/15052748/fileData.do
- **형태**: **XML 파일** (API 아님) — 한 번 받아 로컬에서 RAG 인덱싱
- **데이터**: 인물 16,000명 + 조선 문무과·생원진사시·잡과 합격자 79,000명 통합
- **운영**: 한국학중앙연구원 (`http://people.aks.ac.kr/`)
- **활용**: 인물 질문(단종/정조/이성계/명성황후 등) — 국가유산청 API 인물 정보 갭 보강

### H. 한국천문연구원 특일 정보 OpenAPI ⭐ "오늘의 유산" (서비스키 필요)
- **신청 페이지**: https://www.data.go.kr/data/15012690/openapi.do
- **호출 엔드포인트**: `https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService`
  - `/getRestDeInfo` — 국경일·공휴일
  - `/get24DivisionsInfo` — 24절기
  - `/getHoliDeInfo` — 명절
  - `/getAnniversaryInfo` — 기념일
- **인증**: 서비스키 (자동 승인, 빠름)
- **호출 예시**: `{엔드포인트}/getRestDeInfo?serviceKey={발급키}&solYear=2026&solMonth=06`
- **활용**: discussion.md "오늘의 유산" — 한글날→훈민정음, 5·18→민주화운동 기록물 자동 매핑

---

## 4. P1·확장용 API

### A. 전라남도 남도여행길잡이 전남VR여행 정보
- **페이지**: https://www.data.go.kr/data/15159569/openapi.do
- **활용**: 지역 관광 코스 추천 (P1)

### B. 카카오맵 API
- **개발자 콘솔**: https://developers.kakao.com
- **문서**: https://apis.map.kakao.com
- **활용**: 코스 플래너, 지도 마커, 길찾기 (P1)

---

## 5. 우선순위 — 어떤 순서로 가져올 것인가

### 🔴 1순위 — 즉시 (인증 불필요, 코드만 짜면 됨)
```
국가유산검색 목록 + 상세 (1)
→ 텍스트 설명 풍부, RAG 핵심 데이터

국가유산 이미지검색 (1)
→ 카카오 BasicCard 이미지용
```

### 🟠 2순위 — 답변 품질 결정타 (신청 필요, 자동 승인)
```
한국역대인물 데이터셋 (G) ★★★
→ XML 파일 다운로드, 한 번 받아 인덱싱
→ 인물 질문 답변 품질 갭 메우기 (단종/정조/이성계 등)

4대궁·종묘 상세 (2)
→ 정부 1차 대상 100% 일치, 발표 어필

e뮤지엄 OpenAPI (F) ★★
→ 354개 박물관 250만 점, "심화 설명" 보강
```

### 🟡 3순위 — 기능 연계·확장 (P1)
```
특일 정보 OpenAPI (H)
→ "오늘의 유산" 자동 매핑 (한글날→훈민정음 등)

나레이션 (1) → 사회적 약자 대응 (gov_plan 요건)
행사목록 (1) → 시즌 콘텐츠
공간정보 (1) → 카카오맵 코스 플래너
```

> 신청 작업 선행: data.go.kr 회원가입 → F·H 키 신청(자동 승인) + G 파일 다운로드. 키 발급 기다리는 동안 1순위 코딩 진행 가능.

---

## 6. 호출 → JSON 변환 흐름

> ⚠️ **목록 API만 호출하면 RAG가 빈약함.** 목록은 ID 인덱스고, 진짜 본문 텍스트는 상세 API에 있음. **반드시 2단계 호출** 필요.

```
[1단계] 목록 API → 유산 ID 수집
  requests.get("SearchKindOpenapiList.do", params={ccbaKdcd, ccbaCtcd})
  → ccbaAsno 리스트 추출

       ↓ for each 유산

[2단계] 상세 API → 본문 텍스트 (진짜 RAG 데이터)
  requests.get("SearchKindOpenapiDt.do",
               params={ccbaKdcd, ccbaAsno, ccbaCtcd})
  → 본문 텍스트 추출

  + 이미지 API → 이미지 URL (응답 첨부용 metadata)
  + 위치 API   → 좌표 (P1 지도용 metadata)

       ↓

[3단계] 본문 chunk → 임베딩 → ChromaDB
  splitter.split(본문) → KoSimCSE → collection.add(
    documents=chunks,
    metadatas={이미지URL, 좌표, 종목, 시대 등}
  )
```

### 응답에서 추출할 필드
- 유산명: `<ccbaMnm1>`
- 지역: `<ccbaLcad>`
- 본문 설명: `<content>` (상세 API 응답에 있음 — **이게 RAG 핵심**)
- 이미지: `<imageUrl>` (이미지 API)
- 시대: `<ccceName>`
- 종목: `<ccmaName>`

---

## 7. 빠른 테스트 (브라우저에서)

지금 바로 확인해보고 싶으면:

**서울 지역 국보 목록 보기**
```
http://www.khs.go.kr/cha/SearchKindOpenapiList.do?ccbaKdcd=11&ccbaCtcd=11
```

**경복궁 상세 보기 (4대궁 API)**
```
https://www.heritage.go.kr/heri/gungDetail/gogungListOpenApi.do?gung_number=1
```

브라우저 주소창에 붙여넣으면 XML이 보임. 정상.

---

## 8. 코드로 호출할 때 주의사항

| 항목 | 내용 |
|------|------|
| 인증키 | 필요 없음 (대부분의 cha.go.kr / khs.go.kr API) |
| 포맷 | XML (JSON 아님) |
| CORS | 브라우저 JS 직접 호출 불가 → Python 서버에서 호출 |
| Rate Limit | 명시 없음. 너무 자주 부르지는 말기 |
| 인코딩 | UTF-8 |

---

## 9. 다음 액션

```
□ 1. 브라우저에서 위 URL들 호출해서 데이터 모양 확인
□ 2. fetcher.py 작성 (XML 받아서 heritages.json 만들기)
□ 3. 4대궁 5개 + 전국 주요 유산 20~30개로 시작
□ 4. python rag/indexer.py 재실행
□ 5. python rag/retriever.py 로 답변 품질 확인
```

`fetcher.py` 만들어달라고 하면 바로 작성 가능.
