from app.schemas.chat import Citation
from app.schemas.retrieval import RetrievalResult
from app.services.generation.claim_verifier import ClaimVerifier


def evidence():
    return [RetrievalResult(
        chunk_id="chunk-gyeongbokgung-0",
        document_id="doc-gyeongbokgung",
        heritage_id="gyeongbokgung",
        title="경복궁 sample official document",
        content="경복궁은 조선 왕조의 법궁으로 조선 시대 궁궐 문화와 왕실 의례를 이해하는 핵심 유산이다.",
        source_type="official_db",
        source_trust_level="S1",
        score=1.0,
        score_breakdown={},
    )]


def citation():
    return [Citation(document_id="doc-gyeongbokgung", chunk_id="chunk-gyeongbokgung-0", title="경복궁 sample official document", source_type="official_db", source_trust_level="S1")]


def test_unsupported_year_fails():
    result = ClaimVerifier().verify("경복궁은 1395년에 지어졌습니다.", citation(), evidence(), "heritage_explanation", "ko", "general")
    assert not result["passed"]
    assert any("unsupported_year" in issue for issue in result["issues"])


def test_no_citations_fails():
    result = ClaimVerifier().verify("경복궁은 조선 왕조의 법궁입니다.", [], evidence(), "heritage_explanation", "ko", "general")
    assert not result["passed"]


def test_s1_citation_passes():
    result = ClaimVerifier().verify("경복궁은 조선 왕조의 법궁으로 조선 시대 궁궐 문화와 왕실 의례를 이해하는 핵심 유산이다.", citation(), evidence(), "heritage_explanation", "ko", "general")
    assert result["passed"]
