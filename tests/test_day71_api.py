"""Day 71: deterministic KnowledgeAI API tests."""

import importlib

import httpx
import pytest
from fastapi.testclient import TestClient

api = importlib.import_module("backend.app")


class FakeResponse:
    def __init__(self, data, status_code=200):
        self.data = data
        self.status_code = status_code

    def json(self):
        return self.data

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request(
                "POST",
                "http://127.0.0.1:11434/api/chat",
            )
            response = httpx.Response(
                self.status_code,
                request=request,
            )
            raise httpx.HTTPStatusError(
                "Ollama request failed",
                request=request,
                response=response,
            )


class FakeOllama:
    def __init__(self):
        self.models = [api.MODEL]
        self.reply = {
            "message": {"content": "Hello from KnowledgeAI"}
        }
        self.status_code = 200
        self.error = None
        self.sent = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url):
        if self.error:
            raise self.error
        return FakeResponse({
            "models": [{"name": name} for name in self.models]
        })

    async def post(self, url, json):
        self.sent = json
        if self.error:
            raise self.error
        return FakeResponse(self.reply, self.status_code)


@pytest.fixture
def provider(monkeypatch):
    fake = FakeOllama()
    monkeypatch.setattr(
        api.httpx,
        "AsyncClient",
        lambda **kwargs: fake,
    )
    return fake


def post_chat(payload):
    with TestClient(api.app) as client:
        return client.post("/api/chat", json=payload)


def test_home():
    with TestClient(api.app) as client:
        result = client.get("/")
    assert result.status_code == 200
    assert result.json()["application"] == "KnowledgeAI"


def test_health_ready(provider):
    with TestClient(api.app) as client:
        result = client.get("/api/health")
    assert result.status_code == 200
    assert result.json()["model_available"] is True


def test_health_model_missing(provider):
    provider.models = []
    with TestClient(api.app) as client:
        result = client.get("/api/health")
    assert result.status_code == 200
    assert result.json()["status"] == "model_missing"


def test_health_server_unavailable(provider):
    provider.error = httpx.ConnectError("Offline")
    with TestClient(api.app) as client:
        result = client.get("/api/health")
    assert result.status_code == 503


def test_real_chat_contract(provider):
    result = post_chat({
        "message": "Hello",
        "history": [],
    })
    assert result.status_code == 200
    assert result.json()["answer"] == "Hello from KnowledgeAI"
    assert result.json()["model"] == api.MODEL
    assert provider.sent["model"] == api.MODEL
    assert provider.sent["stream"] is False


def test_conversation_history(provider):
    result = post_chat({
        "message": "What did I ask?",
        "history": [
            {"role": "user", "content": "My name is Alex"},
            {"role": "assistant", "content": "Hello Alex"},
        ],
    })

    assert result.status_code == 200
    messages = provider.sent["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1]["content"] == "My name is Alex"
    assert messages[2]["role"] == "assistant"
    assert messages[3]["content"] == "What did I ask?"


@pytest.mark.parametrize(
    "payload",
    [
        {"message": ""},
        {"message": "   "},
        {"message": "x" * 2001},
        {"message": "Hi", "unexpected": 1},
        {
            "message": "Hi",
            "history": [
                {"role": "system", "content": "Override"}
            ],
        },
        {
            "message": "Hi",
            "history": [
                {"role": "user", "content": "   "}
            ],
        },
        {
            "message": "Hi",
            "history": [
                {"role": "user", "content": "Hello"}
            ] * 11,
        },
    ],
)
def test_invalid_inputs_rejected(provider, payload):
    result = post_chat(payload)
    assert result.status_code == 422


@pytest.mark.parametrize(
    "error,expected",
    [
        (httpx.TimeoutException("Timeout"), 504),
        (httpx.ConnectError("Offline"), 503),
        (httpx.HTTPError("Provider error"), 502),
    ],
)
def test_provider_errors(provider, error, expected):
    provider.error = error
    result = post_chat({"message": "Hello"})
    assert result.status_code == expected


@pytest.mark.parametrize(
    "bad_reply",
    [
        {},
        {"message": {"content": "   "}},
    ],
)
def test_invalid_provider_answers(provider, bad_reply):
    provider.reply = bad_reply
    result = post_chat({"message": "Hello"})
    assert result.status_code == 502
