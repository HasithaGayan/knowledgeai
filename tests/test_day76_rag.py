"""Day 76: API contracts and safety tests with fake embeddings/model.

No network or AI model is needed for these unit tests. Manual Qwen3 tests
must still be performed with the real local Ollama instance.
"""
import json
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.rag_assistant as rag
from backend.semantic_retrieval import SemanticIndex

TOKEN_A = "A" * 43
TOKEN_B = "B" * 43
DOCUMENT = ("FICTIONAL TEST DOCUMENT\nThe workshop fee is LKR 2500.\n"
            "The location is Room B12.\n").encode("utf-8")


def embedder(texts):
    """Deterministic, nonzero same-length embeddings (not real semantic tests)."""
    return [[1.0, 0.1, 0.4] for _ in texts]


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(rag, "_index", lambda: SemanticIndex(tmp_path / "vectors.sqlite3", embedder=embedder))
    app = FastAPI()
    app.include_router(rag.router)
    with TestClient(app) as test_client:
        yield test_client


def headers(token=TOKEN_A, filename="notes.txt"):
    return {"X-KnowledgeAI-Workspace": token, "X-Filename": filename,
            "Content-Type": "application/octet-stream"}


def askheaders(token=TOKEN_A):
    return {"X-KnowledgeAI-Workspace": token, "Content-Type": "application/json"}


def upload(client, *, token=TOKEN_A, filename="notes.txt", content=DOCUMENT):
    return client.post("/api/rag/documents", headers=headers(token, filename), content=content)


def mock_ollama(monkeypatch, *, supported=True, answer="The fee is LKR 2500.",
                quote="The workshop fee is LKR 2500.", fail=None, invalid=False):
    class ModelClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json):
            assert url == rag.OLLAMA_URL
            assert json["format"]["type"] == "object"
            assert "RETRIEVED PASSAGES" in json["messages"][1]["content"]
            if fail is not None:
                raise fail
            body = "nonsense" if invalid else json_module.dumps({
                "supported": supported, "answer": answer, "evidence_quote": quote
            })
            return httpx.Response(200, json={"message": {"content": body}, "done": True},
                                  request=httpx.Request("POST", url))
    json_module = json
    monkeypatch.setattr(rag.httpx, "AsyncClient", lambda **kwargs: ModelClient())


def test_upload_and_list(client):
    response = upload(client)
    assert response.status_code == 201
    assert response.json()["chunk_count"] == 1
    assert response.json()["raw_file_saved"] is False
    assert client.get("/api/rag/documents", headers=headers()).json()["documents"][0]["source"] == "notes.txt"


def test_document_text_persists(client):
    upload(client)
    result = rag._index().search(rag._workspace(TOKEN_A), "fee", top_k=1)
    assert "LKR 2500" in result[0]["text"]


def test_no_documents_no_model_call(client, monkeypatch):
    monkeypatch.setattr(rag.httpx, "AsyncClient", lambda **kwargs: pytest.fail("AI should not run"))
    response = client.post("/api/rag/ask", headers=askheaders(), json={"question": "fee?"})
    assert response.status_code == 200
    assert response.json()["status"] == "no_evidence"
    assert response.json()["sources"] == []


def test_valid_document_answer_cites_real_quote(client, monkeypatch):
    upload(client)
    mock_ollama(monkeypatch)
    response = client.post("/api/rag/ask", headers=askheaders(), json={"question": "What is the fee?"})
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "answered"
    assert result["sources"][0]["source"] == "notes.txt"
    assert result["sources"][0]["evidence_quote"] == "The workshop fee is LKR 2500."


def test_quote_not_in_file_must_abstain(client, monkeypatch):
    upload(client)
    mock_ollama(monkeypatch, quote="The fee is USD 20.")
    result = client.post("/api/rag/ask", headers=askheaders(), json={"question": "Fee?"}).json()
    assert result["status"] == "no_evidence" and result["sources"] == []


def test_model_unsupported_must_abstain(client, monkeypatch):
    upload(client)
    mock_ollama(monkeypatch, supported=False, answer="unknown", quote="")
    result = client.post("/api/rag/ask", headers=askheaders(), json={"question": "Who teaches?"}).json()
    assert result["status"] == "no_evidence" and not result["sources"]


def test_model_malformed_502(client, monkeypatch):
    upload(client)
    mock_ollama(monkeypatch, invalid=True)
    assert client.post("/api/rag/ask", headers=askheaders(), json={"question": "Fee?"}).status_code == 502


def test_model_timeout_504(client, monkeypatch):
    upload(client)
    mock_ollama(monkeypatch, fail=httpx.TimeoutException("timed out"))
    assert client.post("/api/rag/ask", headers=askheaders(), json={"question": "Fee?"}).status_code == 504


def test_missing_workspace_rejected(client):
    assert client.get("/api/rag/documents").status_code == 401
    assert client.post("/api/rag/documents", headers={"X-Filename": "notes.txt",
        "Content-Type": "application/octet-stream"}, content=DOCUMENT).status_code == 401


def test_different_workspace_cannot_see_documents(client):
    upload(client)
    assert client.get("/api/rag/documents", headers=headers(TOKEN_B)).json()["documents"] == []
    response = client.post("/api/rag/ask", headers=askheaders(TOKEN_B), json={"question": "fee?"})
    assert response.json()["status"] == "no_evidence"


def test_delete_scoped_and_successful(client):
    doc_id = upload(client).json()["document_id"]
    assert client.delete("/api/rag/documents/" + doc_id, headers=headers(TOKEN_B)).status_code == 404
    assert client.delete("/api/rag/documents/" + doc_id, headers=headers()).status_code == 204
    assert client.get("/api/rag/documents", headers=headers()).json()["documents"] == []


def test_same_filename_replaces_document(client):
    doc_id = upload(client).json()["document_id"]
    res = upload(client, content=b"The fee has changed to LKR 3000.")
    assert res.json()["document_id"] == doc_id
    out = rag._index().search(rag._workspace(TOKEN_A), "fee", top_k=1)
    assert "3000" in out[0]["text"] and "2500" not in out[0]["text"]


def test_invalid_extension_rejected(client):
    assert upload(client, filename="bad.exe").status_code == 400


def test_path_traversal_rejected(client):
    assert upload(client, filename="../evil.txt").status_code == 400


def test_empty_rejected(client):
    assert upload(client, content=b"").status_code == 400


def test_wrong_content_type_rejected(client):
    h = headers(); h["Content-Type"] = "text/plain"
    assert client.post("/api/rag/documents", headers=h, content=DOCUMENT).status_code == 415


def test_over_limit_rejected(client):
    assert upload(client, content=b"a" * (2_000_001)).status_code == 413


def test_blank_question_rejected(client):
    assert client.post("/api/rag/ask", headers=askheaders(), json={"question": "   "}).status_code == 422


def test_extra_question_fields_rejected(client):
    assert client.post("/api/rag/ask", headers=askheaders(), json={"question": "fee", "hack": 1}).status_code == 422


def test_page_served(client, monkeypatch, tmp_path):
    page = Path(rag.__file__).resolve().parents[1] / "frontend" / "rag.html"
    if page.is_file():
        assert client.get("/rag").status_code == 200


def test_rejects_contradictory_fee_answer(client, monkeypatch):
    upload(client)

    mock_ollama(
        monkeypatch,
        supported=True,
        answer="The AI workshop is free.",
        quote="The workshop fee is LKR 2500."
    )

    response = client.post(
        "/api/rag/ask",
        headers=askheaders(),
        json={"question": "Is the workshop free or paid?"}
    )

    result = response.json()

    assert result["status"] != "answered", (
        "BUG: An answer contradicting its source was accepted."
    )
