# RAG Data Format and Recommendation Logic

## 현재 데이터 적재 상태

- 국가유산 목록 API 기준 전체 대상: 약 17,840건
- 운영 DB에는 `heritages`, `document_chunks` 테이블로 적재한다.
- `heritages.facet_json`에 개인화 답변용 구조화 데이터를 저장한다.
- 임베딩은 비용/시간 때문에 우선 `--no-embed`로 생략하고, 텍스트 검색 기반으로 운영한다. 이후 배치로 임베딩을 추가할 수 있다.

## DB 기본 구조

### `heritages`

주요 컬럼:

- `ccba_kdcd`: 종목 코드
- `ccba_asno`: 관리번호
- `ccba_ctcd`: 지역 코드
- `name`: 국가유산명
- `category`: 국보/보물/사적 등 분류
- `region`: 시도
- `era`: 시대/연대
- `address`: 소재지
- `latitude`, `longitude`: 위도/경도
- `image_url`: 대표 이미지
- `content`: 국가유산청 상세 설명 원문에서 HTML을 제거한 텍스트
- `source_url`: 국가유산청 상세 API URL
- `facet_json`: 관심사별 답변용 구조화 JSON
- `raw_json`: 목록/상세 API 원본 응답

### `document_chunks`

- `heritage_id`: 유산 ID
- `chunk_text`: 검색용 텍스트 조각
- `embedding`: 벡터 임베딩. 현재 전체 적재 단계에서는 비워둘 수 있음
- `metadata_json`: chunk index, source URL 등

## `facet_json` 형식

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
    "status": "auto_extracted",
    "note": "전설 전용 DB가 아니라 상세 설명문에서 이야기성 문장을 자동 추출한 값"
  },
  "people": {
    "label": "인물",
    "evidence": ["왕·장인·소유자·관련 인물 관련 문장"],
    "status": "auto_extracted"
  },
  "travel_visit": {
    "label": "답사/여행",
    "address": "서울 중구 세종대로 40",
    "latitude": 37.559975221378,
    "longitude": 126.975312652739,
    "evidence": ["위치·공개·보관·방문 관련 문장"],
    "nearby_heritages": [
      {
        "name": "근처 국가유산",
        "distance_km": 1.2,
        "category": "사적",
        "region": "서울특별시",
        "address": "..."
      }
    ],
    "related_events": [
      {
        "title": "행사명",
        "place": "장소",
        "date": "2026.05.01 ~ 2026.05.31",
        "url": "https://...",
        "region": "서울특별시",
        "district": "중구"
      }
    ],
    "spatial_api": {
      "url": "https://www.gis-heritage.go.kr/openapi/xmlService/spca.do",
      "status": "available_for_v1"
    },
    "status": "enriched_v1"
  }
}
```

## 관심사별 답변 방식

사용자가 웹 UI에서 관심사를 선택하면 `/api/rag/ask` 요청의 `audience.interests`에 다음 값이 들어간다.

- `architecture`: 건축/공간
- `story`: 이야기/전설
- `people`: 인물
- `travel`: 답사/여행

백엔드는 검색된 국가유산의 `facet_json`을 읽고, 선택된 관심사에 맞는 evidence를 우선 사용한다.

### 건축/공간

- `facet_json.architecture_space.evidence` 사용
- 형태, 구조, 규모, 재료, 배치, 건축 양식을 중심으로 답변한다.

### 이야기/전설

- `facet_json.story_legend.evidence` 사용
- 유래, 발견, 사건, 훼손/복원, 기록상 이야기 흐름을 중심으로 답변한다.
- 현재는 설화 전용 DB가 아니라 상세 설명문 기반 자동 추출이다.

### 인물

- `facet_json.people.evidence` 사용
- 왕, 장인, 소유자, 관련 인물, 제작·수리·기록 주체를 중심으로 답변한다.

### 답사/여행

- `facet_json.travel_visit` 사용
- 주소, 좌표, 방문/공개 관련 문장, 근처 국가유산, 관련 행사를 함께 보여준다.
- 음식점, 카페, 교통, 숙소, 일반 관광지는 v1 범위에서 제외한다.

## 근처 국가유산 추천 방식

1. 검색된 유산의 `latitude`, `longitude`를 확인한다.
2. DB에 좌표가 있는 다른 국가유산들과 거리 계산을 한다.
3. Haversine 방식에 가까운 SQL 계산식으로 km 단위 거리를 구한다.
4. 가까운 순서로 상위 5개를 `nearby_heritages`로 보여준다.

현재 추천 대상은 **운영 DB에 적재된 국가유산 데이터 안에서만** 고른다. 따라서 전체 17,840건 적재가 끝날수록 근처 추천 품질이 좋아진다.

## 관련 행사 추천 방식

1. 행사목록 API `selectEventListOpenapi.do`에서 행사 데이터를 가져온다.
2. 행사 제목, 설명, 장소, 지역, 시군구 텍스트를 합쳐 검색한다.
3. 국가유산명/명칭 일부/지역/시군구가 겹치면 점수를 준다.
4. 점수가 높은 행사를 `related_events`로 붙인다.

현재는 공식 행사-유산 고유키 매칭이 아니라 텍스트 기반 매칭이다. 그래서 지역이 넓게 같은 행사도 포함될 수 있으며, 이후 수동 검수 또는 더 정확한 키가 있으면 개선한다.

## 한계와 다음 개선

- `facet_json` evidence는 키워드 기반 자동 추출이라 완벽하지 않다.
- 행사 매칭은 텍스트 기반이라 일부 넓은 지역 행사가 섞일 수 있다.
- 좌표가 없는 유산은 근처 국가유산 추천이 제한된다.
- 임베딩이 비어 있는 동안은 벡터 검색이 아니라 텍스트 검색 fallback을 쓴다.
- 추후 개선: 전체 임베딩 배치, 행사 매칭 스코어 저장, GIS polygon/WFS 활용, facet 품질 수동 라벨링.
