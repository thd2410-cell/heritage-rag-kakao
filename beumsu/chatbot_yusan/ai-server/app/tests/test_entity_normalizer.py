from app.services.entity_normalizer import EntityNormalizer


def test_korean_typo_maps_to_gyeongbokgung(repo):
    result = EntityNormalizer(repo).normalize("경북궁 설명해줘")
    assert result.detected_entities[0].heritage_id == "gyeongbokgung"
    assert result.detected_entities[0].confidence >= 0.88


def test_romanization_maps_to_gyeongbokgung(repo):
    result = EntityNormalizer(repo).normalize("gyeongbokgung history")
    assert result.detected_entities[0].heritage_id == "gyeongbokgung"
    assert result.detected_entities[0].confidence >= 0.95


def test_english_alias_maps_to_gyeongbokgung(repo):
    result = EntityNormalizer(repo).normalize("Gyeongbokgung Palace")
    assert result.detected_entities[0].heritage_id == "gyeongbokgung"


def test_hanja_maps_to_gyeongbokgung(repo):
    result = EntityNormalizer(repo).normalize("景福宮 설명")
    assert result.detected_entities[0].heritage_id == "gyeongbokgung"


def test_geunjeongjeon_maps(repo):
    result = EntityNormalizer(repo).normalize("geunjeongjeon explain")
    assert result.detected_entities[0].heritage_id == "geunjeongjeon"


def test_unknown_returns_no_confident_entity(repo):
    result = EntityNormalizer(repo).normalize("완전히 모르는 장소")
    assert result.detected_entities == []


def test_khs_typo_short_name_maps_to_sungnyemun(repo):
    repo.ingest_official_dataset(
        {
            "entities": [
                {
                    "id": "khs-11-11-0000010000000",
                    "official_name_ko": "서울 숭례문",
                    "source_trust_level": "S1",
                }
            ],
            "aliases": [
                {
                    "heritage_entity_id": "khs-11-11-0000010000000",
                    "alias": "서울 숭례문",
                    "language": "ko",
                    "alias_type": "official",
                    "confidence_prior": 1.0,
                },
                {
                    "heritage_entity_id": "khs-11-11-0000010000000",
                    "alias": "숭례문",
                    "language": "ko",
                    "alias_type": "local",
                    "confidence_prior": 0.98,
                },
            ],
        }
    )

    result = EntityNormalizer(repo).normalize("숭레문 설명해줘")

    assert result.detected_entities[0].heritage_id == "khs-11-11-0000010000000"
    assert result.detected_entities[0].confidence >= 0.78
