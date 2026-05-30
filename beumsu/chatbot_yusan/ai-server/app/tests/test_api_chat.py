from fastapi.testclient import TestClient

from app.main import app


def test_health():
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}


def test_chat_api():
    client = TestClient(app)
    client.post("/ingest/sample")
    response = client.post("/chat", json={"query": "경북궁 설명해줘", "audience": "general"})
    assert response.status_code == 200
    body = response.json()
    assert body["entities"][0]["heritage_id"] == "gyeongbokgung"
    assert body["citations"]
