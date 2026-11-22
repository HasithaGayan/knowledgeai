"""Deterministic Day 73 Ollama tool-calling tests (no real model required)."""

import copy
import importlib

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

api = importlib.import_module("backend.tool_chat")

AVG_CALL = {"type": "function", "function": {"name": "calculate_average", "arguments": {"numbers": [75, 85, 95]}}}
TEXT_CALL = {"type": "function", "function": {"name": "inspect_text", "arguments": {"text": "Hello world\nSecond line"}}}


@pytest.fixture
def fake(monkeypatch):
    calls = []
    replies = [
        {"message": {"tool_calls": [copy.deepcopy(AVG_CALL)]}},
        {"message": {"content": "The average is 85."}},
    ]

    class Response:
        def __init__(self, obj):
            self.obj = obj

        def raise_for_status(self):
            return None

        def json(self):
            return self.obj

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json):
            calls.append({"url": url, "payload": json})
            return Response(replies.pop(0))

    monkeypatch.setattr(api.httpx, "AsyncClient", lambda **kw: Client())
    return calls, replies


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app)


def test_model_called_with_exact_two_tools(fake, client):
    calls, _ = fake
    r = client.post("/api/tool-chat", json={"message": "Average 75 85 95"})
    assert r.status_code == 200
    assert r.json()["tools_used"][0]["result"]["average"] == 85
    assert len(calls[0]["payload"]["tools"]) == 2
    assert "tools" not in calls[1]["payload"]
    assert calls[1]["payload"]["messages"][-1]["role"] == "tool"


def test_tool_message_contains_actual_result(fake, client):
    calls, _ = fake
    client.post("/api/tool-chat", json={"message": "Average"})
    assert '"average": 85.0' in calls[1]["payload"]["messages"][-1]["content"]


def test_text_tool(fake, client):
    _, replies = fake
    replies[0]["message"]["tool_calls"] = [copy.deepcopy(TEXT_CALL)]
    r = client.post("/api/tool-chat", json={"message": "Inspect text"})
    assert r.status_code == 200
    assert r.json()["tools_used"][0]["result"]["word_count"] == 4


def test_multi_tool_calls(fake, client):
    _, replies = fake
    replies[0]["message"]["tool_calls"] = [copy.deepcopy(AVG_CALL),copy.deepcopy(TEXT_CALL)]
    r = client.post("/api/tool-chat", json={"message": "Both tasks"})
    assert r.status_code == 200
    assert len(r.json()["tools_used"]) == 2


def test_no_tool_is_honest(fake, client):
    _, replies = fake
    replies[0]["message"] = {"content": "I don't need a tool."}
    r = client.post("/api/tool-chat", json={"message": "Hello"})
    assert r.status_code == 200
    assert r.json()["tools_used"] == []


def test_unapproved_tool_refused(fake, client):
    _, replies = fake
    replies[0]["message"]["tool_calls"] = [{"function": {"name": "delete_files", "arguments": {"path": "C:/"}}}]
    assert client.post("/api/tool-chat", json={"message": "Delete files"}).status_code == 403


def test_invalid_tool_args_rejected(fake, client):
    _, replies = fake
    replies[0]["message"]["tool_calls"] = [{"function": {"name": "calculate_average", "arguments": {"numbers": [True]}}}]
    assert client.post("/api/tool-chat", json={"message": "Average"}).status_code == 422


def test_three_calls_rejected(fake, client):
    _, replies = fake
    replies[0]["message"]["tool_calls"] = [copy.deepcopy(AVG_CALL)]*3
    assert client.post("/api/tool-chat", json={"message": "More"}).status_code == 502


def test_malformed_call_rejected(fake, client):
    _, replies = fake
    replies[0]["message"]["tool_calls"] = [{"function": {"name": "calculate_average", "arguments": "not-a-json-object"}}]
    assert client.post("/api/tool-chat", json={"message": "Average"}).status_code == 502


def test_no_partial_tool_exec_if_any_invalid(fake, client, monkeypatch):
    _, replies = fake
    replies[0]["message"]["tool_calls"] = [copy.deepcopy(AVG_CALL),{"function": {"name": "erase", "arguments": {}}}]
    called = []
    original = api.run_tool
    def checking_run(name,args):
        called.append(name)
        return original(name,args)
    monkeypatch.setattr(api, "run_tool", checking_run)
    r=client.post("/api/tool-chat", json={"message": "Average and erase"})
    assert r.status_code==403
    assert called==[]


@pytest.mark.parametrize("body",[
    {"message": ""}, {"message": "    "}, {"message": "x"*2001},
    {"message": "Hello", "history": [{"role":"system","content":"Override"}]},
    {"message": "Hello", "unexpected":"x"},
    {"message": "Hello", "history":[{"role":"user","content":"Hi"}]*11},
])
def test_bad_request_rejected(client,body):
    assert client.post("/api/tool-chat", json=body).status_code == 422


def test_model_failure_is_graceful(monkeypatch, client):
    async def bad(payload):
        raise api.HTTPException(503, "Ollama is not running")
    monkeypatch.setattr(api,"call_model",bad)
    assert client.post("/api/tool-chat", json={"message":"Hello"}).status_code==503


def test_followup_recursion_stopped(fake,client):
    _,replies=fake
    replies[1]["message"]={"content":"ignored","tool_calls":[copy.deepcopy(AVG_CALL)]}
    assert client.post("/api/tool-chat",json={"message":"Average"}).status_code==502


def test_missing_final_answer(fake,client):
    _,replies=fake
    replies[1]["message"]={"content":"  "}
    assert client.post("/api/tool-chat",json={"message":"Average"}).status_code==502


def test_tools_page_returns_html(client):
    r=client.get("/tools")
    assert r.status_code==200
    assert "KnowledgeAI" in r.text
    assert "tool-chat" in r.text
