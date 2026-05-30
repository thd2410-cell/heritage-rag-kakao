from app.schemas.chat import ChatRequest
from app.services.orchestrator import ChatOrchestrator


def test_chat_typo_returns_cited_gyeongbokgung_answer(repo):
    response = ChatOrchestrator(repo).chat(ChatRequest(query="경북궁 설명해줘"))
    assert "경복궁" in response.answer
    assert response.entities[0].heritage_id == "gyeongbokgung"
    assert response.citations


def test_chat_english_returns_english_and_entity(repo):
    response = ChatOrchestrator(repo).chat(ChatRequest(query="gyeongbokgung history in English"))
    assert response.detected_language == "en"
    assert response.entities[0].heritage_id == "gyeongbokgung"
    assert "Gyeongbokgung" in response.answer
    assert response.citations


def test_route_request_returns_route(repo):
    response = ChatOrchestrator(repo).chat(ChatRequest(query="고령자용 경복궁 1시간 코스 추천해줘", audience="elderly"))
    assert response.intent == "route_recommendation"
    assert response.route is not None
    assert response.route["stops"]


def test_answer_has_citations(repo):
    response = ChatOrchestrator(repo).chat(ChatRequest(query="근정전이 뭐야?"))
    assert response.citations
