# Heritage Chat JSON v1 Format

1차 버전 목적: 국가유산청/국가유산 공간정보 쪽 공공 API를 사용해 챗봇 답변에 쓸 수 있는 정규화 JSON을 만든다.

**포함:** 국가유산 목록, 상세, 위치 좌표/공간정보 출처, 국가유산 행사 목록 매칭, 생성된 데이터셋 안의 근처 국가유산 후보.  
**제외:** 교통, 맛집, 카페, 숙소, 일반 관광지 등 외부 관광 정보.

## 사용 API

- 목록: `https://www.khs.go.kr/cha/SearchKindOpenapiList.do`
- 상세: `https://www.khs.go.kr/cha/SearchKindOpenapiDt.do`
- 위치/공간정보: `https://www.gis-heritage.go.kr/openapi/xmlService/spca.do`
- 행사목록: `https://www.khs.go.kr/cha/openapi/selectEventListOpenapi.do`

## 생성 명령

```bash
python3 scripts/build_heritage_json_v1.py --limit 20 --event-limit 100 --output data/heritage_v1_sample.json
```

옵션:

```bash
python3 scripts/build_heritage_json_v1.py \
  --regions 11 37 \
  --categories 11 12 13 \
  --limit 100 \
  --event-limit 300 \
  --output data/heritage_v1.json
```

- `regions`: 국가유산청 지역 코드. 기본값 `11` 서울, `37` 경북
- `categories`: 종목 코드. 기본값 `11` 국보, `12` 보물, `13` 사적
- `event-limit`: 행사 API에서 가져와 매칭할 행사 수

## Top-level shape

```json
{
  "schema_version": "heritage-chat.dataset.v1",
  "generated_at": "2026-05-31T00:00:00+00:00",
  "count": 1,
  "enrichment": {
    "location_api": "https://www.gis-heritage.go.kr/openapi/xmlService/spca.do",
    "event_api": "https://www.khs.go.kr/cha/openapi/selectEventListOpenapi.do",
    "event_count_fetched": 100,
    "nearby_scope_v1": "same district first, then same region within generated dataset",
    "excluded_v1": ["traffic", "restaurants", "cafes", "non-heritage tourist spots"]
  },
  "records": []
}
```

## Record shape

```json
{
  "schema_version": "heritage-chat.normalized.v1",
  "id": "11-0000010000000-11",
  "codes": {
    "ccba_kdcd": "11",
    "ccba_asno": "0000010000000",
    "ccba_ctcd": "11",
    "ccba_cpno": "1111100010000"
  },
  "names": {
    "ko": "서울 숭례문",
    "hanja": "서울 崇禮門"
  },
  "classification": {
    "designation": "국보",
    "gcode": "유적건조물",
    "bcode": "정치국방",
    "mcode": "성",
    "scode": "성곽시설"
  },
  "location": {
    "region": "서울특별시",
    "district": "중구",
    "address": "서울 중구 세종대로 40 (남대문로4가)",
    "latitude": 37.559975221378,
    "longitude": 126.975312652739
  },
  "period": {
    "era_text": "조선 태조 7년(1398)",
    "designated_date": "19621220"
  },
  "management": {
    "quantity": "1동",
    "owner": "국유",
    "manager": "국가유산청 덕수궁관리소",
    "cancelled": "N"
  },
  "media": {
    "image_url": "http://...jpg"
  },
  "description": {
    "source_text": "상세 API 원문 설명에서 HTML을 제거한 텍스트",
    "summary_v1": "앞부분 3문장 자동 요약"
  },
  "answer_facets": {
    "architecture_space": {
      "label": "건축/공간",
      "evidence": ["형태·구조 관련 자동 추출 문장"],
      "status": "auto_extracted"
    },
    "story_legend": {
      "label": "이야기/전설",
      "evidence": ["유래·사건·발견 관련 자동 추출 문장"],
      "status": "auto_extracted",
      "note": "전설 전용 데이터가 아니라 상세 설명문에서 이야기성 문장을 자동 추출한 값입니다."
    },
    "people": {
      "label": "인물",
      "evidence": ["인물 관련 자동 추출 문장"],
      "status": "auto_extracted"
    },
    "travel_visit": {
      "label": "답사/여행",
      "address": "서울 중구 세종대로 40 (남대문로4가)",
      "latitude": 37.559975221378,
      "longitude": 126.975312652739,
      "spatial_api": {
        "url": "https://www.gis-heritage.go.kr/openapi/xmlService/spca.do",
        "status": "available_for_v1",
        "note": "국가유산 공간정보 API는 지정구역/보호구역 등 공간 레이어 보강용입니다. 1차 JSON에는 목록/상세 좌표를 기본 위치로 넣고, 공간 API 출처를 함께 기록합니다."
      },
      "evidence": ["위치·보관·공개 관련 자동 추출 문장"],
      "nearby_heritages": [
        {
          "id": "11-0000020000000-11",
          "name": "서울 원각사지 십층석탑",
          "designation": "국보",
          "region": "서울특별시",
          "district": "종로구",
          "address": "서울 종로구 ...",
          "latitude": 37.57,
          "longitude": 126.98,
          "match_basis": "same_region"
        }
      ],
      "events": [
        {
          "event_id": "4569",
          "title": "북악산 한양도성 자율입산제 시행 안내",
          "description": "HTML 제거된 행사 설명",
          "start_date": "20230101",
          "end_date": "20331231",
          "date_text": "2023. 01. 01 ~ 2033. 12. 31",
          "venue": "북악산",
          "region": "서울특별시",
          "district": "",
          "organizer": "",
          "contact": ".",
          "target": "",
          "price": "",
          "url": "https://...",
          "source": "selectEventListOpenapi"
        }
      ],
      "status": "enriched_v1",
      "note": "근처 맛집/교통은 제외합니다. 근처 국가유산과 국가유산 행사만 공공 API 기반으로 보강합니다."
    }
  },
  "source": {
    "list_url": "https://www.khs.go.kr/cha/SearchKindOpenapiList.do",
    "detail_url": "https://www.khs.go.kr/cha/SearchKindOpenapiDt.do?...",
    "gis_location_url": "https://www.gis-heritage.go.kr/openapi/xmlService/spca.do",
    "event_url": "https://www.khs.go.kr/cha/openapi/selectEventListOpenapi.do",
    "fetched_at": "2026-05-31T00:00:00+00:00"
  },
  "raw": {
    "list": {},
    "detail": {}
  }
}
```

## 1차 버전 한계

- `story_legend`는 실제 설화/전설 DB가 아니라 상세 설명문에서 자동 추출한 이야기성 문장이다.
- `nearby_heritages`는 생성된 JSON 데이터셋 안에서 같은 시군구/지역 기준으로 고른다. 외부 맛집·교통·일반 관광지는 넣지 않는다.
- `events`는 행사 목록 API의 지역/장소/명칭 텍스트 매칭 기반이다. 정확한 행사-유산 매핑은 이후 별도 키나 수동 검수가 있으면 좋아진다.
- 공간정보 API는 v1에서 출처와 보강 가능성을 명시하고, 기본 좌표는 목록/상세 API의 위경도를 사용한다. 지정구역 polygon까지 쓰는 것은 v2에서 WFS 파라미터 확정 후 확장한다.
- 자동 추출 품질은 데이터 라벨링 없이 키워드 기반이므로, 이후 사람이 라벨링하거나 별도 facet DB를 추가하면 좋아진다.
