# Heritage Chat JSON v1 Format

1차 버전 목적: 국가유산청 **검색 목록** + **검색 상세** API만 사용해서 챗봇 답변에 쓸 수 있는 정규화 JSON을 만든다.

근처 여행지, 행사, GIS 보강은 v2 이후로 미룬다.

## 사용 API

- 목록: `https://www.khs.go.kr/cha/SearchKindOpenapiList.do`
- 상세: `https://www.khs.go.kr/cha/SearchKindOpenapiDt.do`

## 생성 명령

```bash
python scripts/build_heritage_json_v1.py --limit 20 --output data/heritage_v1_sample.json
```

옵션:

```bash
python scripts/build_heritage_json_v1.py \
  --regions 11 37 \
  --categories 11 12 13 \
  --limit 100 \
  --output data/heritage_v1.json
```

- `regions`: 국가유산청 지역 코드. 기본값 `11` 서울, `37` 경북
- `categories`: 종목 코드. 기본값 `11` 국보, `12` 보물, `13` 사적

## Top-level shape

```json
{
  "schema_version": "heritage-chat.dataset.v1",
  "generated_at": "2026-05-31T00:00:00+00:00",
  "count": 1,
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
      "evidence": ["위치·보관·공개 관련 자동 추출 문장"],
      "nearby_places": [],
      "events": [],
      "status": "partial_v1",
      "note": "근처 여행지와 행사는 v2에서 위치정보/행사 API로 보강합니다."
    }
  },
  "source": {
    "list_url": "https://www.khs.go.kr/cha/SearchKindOpenapiList.do",
    "detail_url": "https://www.khs.go.kr/cha/SearchKindOpenapiDt.do?...",
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
- `travel_visit.nearby_places`는 비워둔다. 근처 여행지는 위치정보 API 또는 외부 지도/관광 API 결합이 필요하다.
- `travel_visit.events`는 비워둔다. 행사 API 결합은 v2에서 별도 매칭 로직이 필요하다.
- 자동 추출 품질은 데이터 라벨링 없이 키워드 기반이므로, 이후 사람이 라벨링하거나 별도 facet DB를 추가하면 좋아진다.
