import json

from app.schemas.retrieval import RetrievalRequest
from app.services.ingest.khs_client import KhsOpenApiClient
from app.services.ingest.loaders import OfficialDataLoader
from app.services.retrieval.hybrid_retriever import HybridRetriever


def test_official_json_ingest_with_images(repo, tmp_path):
    source = tmp_path / "official.json"
    source.write_text(
        json.dumps(
            {
                "entities": [
                    {
                        "id": "official-test-heritage",
                        "official_name_ko": "테스트유산",
                        "official_name_en": "Test Heritage",
                        "source_trust_level": "S1",
                    }
                ],
                "aliases": [
                    {
                        "heritage_entity_id": "official-test-heritage",
                        "alias": "테스트유산",
                        "language": "ko",
                        "alias_type": "official",
                    }
                ],
                "documents": [
                    {
                        "id": "official-test-doc",
                        "heritage_entity_id": "official-test-heritage",
                        "title": "테스트유산 공식 문서",
                        "source_type": "official_db",
                        "source_trust_level": "S1",
                        "language": "ko",
                        "content": "테스트유산은 공식 데이터 적재 테스트를 위한 문서입니다.",
                    }
                ],
                "images": [
                    {
                        "heritage_entity_id": "official-test-heritage",
                        "title": "Test image",
                        "image_url": "https://example.local/test.jpg",
                        "caption": "Official image caption",
                        "source_trust_level": "S1",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    dataset = OfficialDataLoader().load(source)
    result = repo.ingest_official_dataset(dataset)

    assert result["entities"] == 1
    assert result["aliases"] == 1
    assert result["documents"] == 1
    assert result["chunks"] == 1
    assert result["images"] == 1
    images = repo.list_images_for_entities(["official-test-heritage"])
    assert len(images) == 1
    assert images[0].image_url == "https://example.local/test.jpg"
    results = HybridRetriever(repo).retrieve(
        RetrievalRequest(query="테스트유산", normalized_entities=[], top_k=5)
    )
    assert any(item.heritage_id == "official-test-heritage" for item in results)


def test_khs_image_xml_parser():
    xml = """
    <result>
      <item>
        <ccimNm>Gyeongbokgung image</ccimNm>
        <imageUrl>https://www.khs.go.kr/example.jpg</imageUrl>
        <ccimDesc>Official caption</ccimDesc>
        <imageNuri>public</imageNuri>
      </item>
      <item>
        <ccimNm>Missing URL</ccimNm>
      </item>
    </result>
    """

    rows = KhsOpenApiClient().parse_image_xml(xml)

    assert len(rows) == 1
    assert rows[0]["title"] == "Gyeongbokgung image"
    assert rows[0]["image_url"] == "https://www.khs.go.kr/example.jpg"
    assert rows[0]["caption"] == "Official caption"


def test_khs_list_detail_to_dataset_parser():
    client = KhsOpenApiClient()
    list_xml = """
    <result>
      <totalCnt>1</totalCnt>
      <pageUnit>10</pageUnit>
      <pageIndex>1</pageIndex>
      <item>
        <ccbaMnm1>경복궁</ccbaMnm1>
        <ccbaMnm2>景福宮</ccbaMnm2>
        <ccmaName>사적</ccmaName>
        <ccbaKdcd>13</ccbaKdcd>
        <ccbaCtcd>11</ccbaCtcd>
        <ccbaAsno>01170000</ccbaAsno>
        <longitude>126.9769</longitude>
        <latitude>37.5796</latitude>
      </item>
    </result>
    """
    detail_xml = """
    <result>
      <item>
        <ccbaMnm1>경복궁</ccbaMnm1>
        <ccbaMnm2>景福宮</ccbaMnm2>
        <ccbaLcad>서울특별시 종로구</ccbaLcad>
        <ccceName>조선</ccceName>
        <content>경복궁은 조선 왕조의 법궁이다.</content>
      </item>
    </result>
    """

    listed = client.parse_list_xml(list_xml)
    detail = client.parse_detail_xml(detail_xml)
    row = {**listed["items"][0], **detail}

    assert listed["total_count"] == 1
    assert client.entity_id(row) == "khs-13-11-01170000"
    assert "경복궁은 조선 왕조의 법궁이다." in client._document_content(row)
