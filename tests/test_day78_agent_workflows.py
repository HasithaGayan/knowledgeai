"""Day 78: executable security, human approval, tracing, and workflow tests."""
from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend import agent_workflows as api

TOKEN_A = "a" * 43
TOKEN_B = "b" * 43
SAMPLE_TEXT = "Python practice includes machine learning and several exercises."


@pytest.fixture
def test_env(tmp_path, monkeypatch):
    monkeypatch.setenv("KNOWLEDGEAI_AGENT_DB", str(tmp_path / "db" / "agent.sqlite3"))
    monkeypatch.setenv("KNOWLEDGEAI_AGENT_REPORTS", str(tmp_path / "reports"))

    async def fake_summary(text, metrics, average):
        return "Summary of the supplied learning notes.", True

    monkeypatch.setattr(api, "_model_summary", fake_summary)
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app), tmp_path


def headers(token=TOKEN_A):
    return {"X-KnowledgeAI-Workspace": token}


def make(client, **kwargs):
    payload = {"title": "Workshop brief", "text": SAMPLE_TEXT, "numbers": [75, 85, 95]}
    payload.update(kwargs)
    return client.post("/api/agent/workflows", json=payload, headers=headers())


def test_pending_requires_human_approval(test_env):
    client, root = test_env
    r = make(client)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["status"] == "pending"
    assert len(data["plan"]) == 6
    assert [x["step"] for x in data["trace"]] == [
        "triage", "inspect_text", "calculate_average", "draft_brief", "human_approval"]
    assert not list((root / "reports").rglob("*.md"))
    assert client.get(f"/api/agent/workflows/{data['id']}/report", headers=headers()).status_code == 403


def test_approve_writes_one_report_and_downloads(test_env):
    client, root = test_env
    made = make(client).json()
    result = client.post(f"/api/agent/workflows/{made['id']}/decision", json={"approve": True}, headers=headers())
    assert result.status_code == 200
    assert result.json()["file_saved"] is True
    assert len(list((root / "reports").rglob("*.md"))) == 1
    doc = client.get(f"/api/agent/workflows/{made['id']}/report", headers=headers())
    assert doc.status_code == 200
    assert b"Verified calculations" in doc.content
    assert b"85.0" in doc.content
    item = client.get(f"/api/agent/workflows/{made['id']}", headers=headers()).json()
    assert item["status"] == "approved"
    assert item["trace"][-1]["step"] == "save_local_report"
    assert item["trace"][-1]["details"]["user_approved"] is True


def test_reject_creates_no_report(test_env):
    client, root = test_env
    made = make(client).json()
    response = client.post(f"/api/agent/workflows/{made['id']}/decision", json={"approve": False}, headers=headers())
    assert response.json() == {"id": made["id"], "status": "rejected", "file_saved": False}
    assert not list((root / "reports").rglob("*.md"))
    assert client.get(f"/api/agent/workflows/{made['id']}/report", headers=headers()).status_code == 403


def test_no_double_approval(test_env):
    client, root = test_env
    made = make(client).json()
    path = f"/api/agent/workflows/{made['id']}/decision"
    assert client.post(path, json={"approve": True}, headers=headers()).status_code == 200
    assert client.post(path, json={"approve": True}, headers=headers()).status_code == 409
    assert len(list((root / "reports").rglob("*.md"))) == 1


def test_reject_cannot_be_approved_later(test_env):
    client, _ = test_env
    ident = make(client).json()["id"]
    path = f"/api/agent/workflows/{ident}/decision"
    assert client.post(path, json={"approve": False}, headers=headers()).status_code == 200
    assert client.post(path, json={"approve": True}, headers=headers()).status_code == 409


def test_workspace_isolation(test_env):
    client, _ = test_env
    ident = make(client).json()["id"]
    url = f"/api/agent/workflows/{ident}"
    assert client.get(url, headers=headers(TOKEN_B)).status_code == 404
    assert client.post(url + "/decision", json={"approve": True}, headers=headers(TOKEN_B)).status_code == 404
    assert client.get("/api/agent/workflows", headers=headers(TOKEN_B)).json() == {"workflows": []}
    assert client.get(url, headers=headers(TOKEN_A)).status_code == 200


def test_missing_or_invalid_workspace_rejected(test_env):
    client, _ = test_env
    payload = {"title": "Workshop", "text": SAMPLE_TEXT}
    assert client.post("/api/agent/workflows", json=payload).status_code == 401
    assert client.post("/api/agent/workflows", json=payload, headers=headers("x")).status_code == 401


@pytest.mark.parametrize("changes", [
    {"title": "  "}, {"text": "  "}, {"numbers": [True]},
    {"numbers": ["75"]}, {"numbers": [None]},
    {"numbers": [1e9]}, {"numbers": list(range(21))},
    {"evil": True},
])
def test_invalid_payload_rejected(test_env, changes):
    client, root = test_env
    assert make(client, **changes).status_code == 422
    assert not list((root / "reports").rglob("*.md"))


def test_optional_calculator_not_executed(test_env):
    client, _ = test_env
    result = make(client, numbers=[]).json()
    assert result["status"] == "pending"
    assert "calculate_average" not in result["plan"]
    assert "Average of" not in result["draft"]


def test_trace_does_not_log_private_notes_or_tokens(test_env):
    client, _ = test_env
    private = "Important private exercise details with one example for trainees."
    data = make(client, text=private).json()
    trace = str(data["trace"])
    assert private not in trace and TOKEN_A not in trace
    assert "model" in trace


def test_model_unavailable_uses_explicit_fallback(test_env, monkeypatch):
    client, _ = test_env
    async def fail_model(text, metrics, average):
        return "AI summary unavailable; only the verified metrics below are included.", False
    monkeypatch.setattr(api, "_model_summary", fail_model)
    response = make(client)
    assert response.status_code == 201
    data = response.json()
    assert "AI summary unavailable" in data["draft"]
    assert any(t["step"] == "draft_brief" and t["status"] == "fallback" for t in data["trace"])


def test_approval_expiry_prevents_save(test_env):
    client, root = test_env
    ident = make(client).json()["id"]
    with api._connection() as db:
        db.execute("UPDATE agent_runs SET expires_utc=? WHERE id=?", ("2000-01-01T00:00:00+00:00", ident))
    r = client.post(f"/api/agent/workflows/{ident}/decision", json={"approve": True}, headers=headers())
    assert r.status_code == 409
    assert not list((root / "reports").rglob("*.md"))


def test_bad_ident_cannot_traverse(test_env):
    client, _ = test_env
    assert client.get("/api/agent/workflows/not-an-id", headers=headers()).status_code == 404


def test_local_only_check():
    from types import SimpleNamespace
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as info:
        api._local(SimpleNamespace(client=SimpleNamespace(host="203.0.113.10")))
    assert info.value.status_code == 403


def test_only_known_tools_used(test_env, monkeypatch):
    client, _ = test_env
    seen = []
    original = api.run_tool
    def track(name, args):
        seen.append(name)
        return original(name, args)
    monkeypatch.setattr(api, "run_tool", track)
    assert make(client).status_code == 201
    assert seen == ["inspect_text", "calculate_average"]


def test_history_persists_between_client_calls(test_env):
    client, _ = test_env
    made = make(client).json()
    another = client.get("/api/agent/workflows", headers=headers()).json()
    assert another["workflows"][0]["id"] == made["id"]


def test_agent_page_works_when_installed(test_env):
    client, _ = test_env
    r = client.get("/agent")
    if (Path(api.__file__).resolve().parents[1] / "frontend" / "agent.html").exists():
        assert r.status_code == 200 and "Agent Studio" in r.text
