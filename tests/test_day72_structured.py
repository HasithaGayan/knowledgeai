"""Day 72 structured response validation and failure recovery tests.

The provider is mocked; test real local model manually in the website.
"""
import json
import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import app
import backend.structured_output as structured


VALID = {
    "status": "answered",
    "topic": "AI and ML",
    "answer": "Supervised learning uses labeled data.",
    "source_status": "no_document_sources",
}


class MockReply:
    def __init__(self, body, code=200):
        self.body = body
        self.code = code

    def json(self):
        return self.body

    def raise_for_status(self):
        if self.code >= 400:
            request = httpx.Request("POST", structured.OLLAMA_URL)
            response = httpx.Response(self.code, request=request)
            raise httpx.HTTPStatusError("Provider error", request=request, response=response)


class MockOllama:
    def __init__(self):
        self.output = VALID.copy()
        self.error = None
        self.sent = None
        self.done_reason = "stop"
        self.code = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json):
        self.sent = json
        if self.error is not None:
            raise self.error
        return MockReply({
            "message": {"content": __import__('json').dumps(self.output)},
            "done_reason": self.done_reason,
        }, self.code)


@pytest.fixture
def model(monkeypatch):
    provider = MockOllama()
    monkeypatch.setattr(structured.httpx, "AsyncClient", lambda **kwargs: provider)
    return provider


def ask(payload):
    with TestClient(app) as client:
        return client.post("/api/structured-answer", json=payload)


def test_structured_page():
    with TestClient(app) as client:
        response = client.get("/structured")
    assert response.status_code == 200
    assert 'id="structured-form"' in response.text


def test_valid_answer(model):
    response = ask({"question": "What is supervised learning?"})
    assert response.status_code == 200
    assert response.json() == VALID


def test_json_schema_used(model):
    ask({"question": "What is ML?"})
    assert isinstance(model.sent["format"], dict)
    assert "properties" in model.sent["format"]
    assert model.sent["stream"] is False
    assert model.sent["think"] is False


def test_question_sent_after_system_prompt(model):
    ask({"question": "  Explain lists  "})
    messages = model.sent["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1] == {"role": "user", "content": "Explain lists"}


@pytest.mark.parametrize("payload", [
    {}, {"question": ""}, {"question": "   "},
    {"question": "A" * 801},
    {"question": "Hi", "unknown": "x"},
])
def test_invalid_input_rejected(model, payload):
    assert ask(payload).status_code == 422


def test_refusal_valid(model):
    model.output = {**VALID, "status": "refused", "answer": "I cannot help with that request."}
    response = ask({"question": "Example"})
    assert response.status_code == 200
    assert response.json()["status"] == "refused"


def test_needs_clarification_valid(model):
    model.output = {**VALID, "status": "needs_clarification", "answer": "What do you mean?"}
    assert ask({"question": "Explain it."}).json()["status"] == "needs_clarification"


def test_fabricated_document_sources_rejected(model):
    model.output = {**VALID, "source_status": "documents_searched"}
    assert ask({"question": "Explain ML"}).status_code == 502


def test_missing_answer_rejected(model):
    model.output = {"status": "answered", "topic": "AI and ML", "source_status": "no_document_sources"}
    assert ask({"question": "Explain ML"}).status_code == 502


def test_invalid_status_rejected(model):
    model.output = {**VALID, "status": "super_confident"}
    assert ask({"question": "Explain ML"}).status_code == 502


def test_extra_property_rejected(model):
    model.output = {**VALID, "made_up_citation": "source.pdf"}
    assert ask({"question": "Explain ML"}).status_code == 502


def test_incomplete_generation_rejected(model):
    model.done_reason = "length"
    assert ask({"question": "Explain ML"}).status_code == 502


@pytest.mark.parametrize("failure,expected", [
    (httpx.TimeoutException("timed out"), 504),
    (httpx.ConnectError("offline"), 503),
    (httpx.HTTPError("failure"), 502),
])
def test_provider_errors(model, failure, expected):
    model.error = failure
    assert ask({"question": "Explain AI"}).status_code == expected


def test_provider_http_500(model):
    model.code = 500
    assert ask({"question": "Explain AI"}).status_code == 502
