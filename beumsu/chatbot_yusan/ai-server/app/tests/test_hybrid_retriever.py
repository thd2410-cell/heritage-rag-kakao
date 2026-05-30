from app.schemas.retrieval import RetrievalRequest
from app.services.entity_normalizer import EntityNormalizer
from app.services.retrieval.hybrid_retriever import HybridRetriever


def test_gyeongbokgung_query_returns_gyeongbokgung_chunks(repo):
    entities = EntityNormalizer(repo).normalize("경복궁 설명").detected_entities
    results = HybridRetriever(repo).retrieve(RetrievalRequest(query="경복궁 설명", normalized_entities=entities))
    assert results[0].heritage_id == "gyeongbokgung"
    assert results[0].source_trust_level == "S1"


def test_geunjeongjeon_returns_related_gyeongbokgung(repo):
    entities = EntityNormalizer(repo).normalize("근정전 설명").detected_entities
    results = HybridRetriever(repo).retrieve(RetrievalRequest(query="근정전 설명", normalized_entities=entities, top_k=5))
    ids = {r.heritage_id for r in results}
    assert "geunjeongjeon" in ids
    assert "gyeongbokgung" in ids


def test_entity_filter_prioritizes_selected_entity(repo):
    entities = EntityNormalizer(repo).normalize("종묘 알려줘").detected_entities
    results = HybridRetriever(repo).retrieve(RetrievalRequest(query="종묘 알려줘", normalized_entities=entities))
    assert results[0].heritage_id == "jongmyo"
