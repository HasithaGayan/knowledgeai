"""Day 71: verify the local frontend integration without model inference."""
from fastapi.testclient import TestClient
from backend.app import app


def test_chat_page_served():
    with TestClient(app) as client:
        response = client.get("/chat")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "KnowledgeAI" in response.text
    assert 'id="chat-form"' in response.text
    assert 'id="message-input"' in response.text


def test_api_home_preserved():
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert response.json()["application"] == "KnowledgeAI"


def test_openapi_still_available():
    with TestClient(app) as client:
        response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "/api/chat" in response.json()["paths"]
