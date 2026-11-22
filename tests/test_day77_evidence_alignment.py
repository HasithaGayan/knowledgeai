"""Day 77: literal source alignment, a narrow repair for wrong model quotes."""
import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.rag_assistant as rag
from backend.evidence_alignment import select_evidence_quote
from backend.semantic_retrieval import SemanticIndex

DATE_SENTENCE = "The AI workshop will take place on 15 December 2026."
FEE_SENTENCE = "The workshop fee is LKR 2500."
TEXT = f"FICTIONAL TEST DOCUMENT\n{DATE_SENTENCE}\n{FEE_SENTENCE}\nThe venue is Room B12."
PASSAGE = {"source": "notes.txt", "chunk_number": 1, "document_id": "doc", "score": 0.6, "text": TEXT}


@pytest.mark.parametrize("answer,quote,expected", [
    ("15 December 2026", FEE_SENTENCE, DATE_SENTENCE),
    ("The event is on 15 December 2026.", DATE_SENTENCE, DATE_SENTENCE),
    ("The fee is LKR 2500.", FEE_SENTENCE, FEE_SENTENCE),
    ("It costs LKR 3000.", FEE_SENTENCE, None),
    ("The AI workshop is free.", FEE_SENTENCE, None),
    ("16 December 2026", FEE_SENTENCE, None),
    ("15 December 2026 and 16 December 2026", FEE_SENTENCE, None),
    ("15 December 2026", "The event is on 10 December 2026.", DATE_SENTENCE),
    ("15 December 2026", "", DATE_SENTENCE),
    ("The workshop is free on 15 December 2026", DATE_SENTENCE, None),
    ("The fee is LKR 3000 and the date is 15 December 2026", FEE_SENTENCE, None),
])
def test_alignment_cases(answer, quote, expected):
    chosen = select_evidence_quote(answer, quote, [PASSAGE])
    if expected is None:
        assert chosen is None
    else:
        assert chosen is not None
        assert chosen[0] is PASSAGE
        assert chosen[1] == expected
        assert chosen[1] in PASSAGE["text"]


def test_not_cited_from_other_document():
    irrelevant = dict(PASSAGE, text="The meeting is in Room B12.", source="wrong.txt")
    chosen = select_evidence_quote("15 December 2026", FEE_SENTENCE, [irrelevant, PASSAGE])
    assert chosen and chosen[0]["source"] == "notes.txt"


def test_no_fallback_without_exact_date():
    chosen = select_evidence_quote("The date is next month", FEE_SENTENCE, [PASSAGE])
    assert chosen is None


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(
        rag, "_index", lambda: SemanticIndex(tmp_path / "vectors.sqlite3", embedder=lambda texts: [[1., 0., 0.] for _ in texts])
    )
    app = FastAPI()
    app.include_router(rag.router)
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/rag/documents",
            headers={"X-KnowledgeAI-Workspace": "A" * 43,
                     "X-Filename": "notes.txt", "Content-Type": "application/octet-stream"},
            content=TEXT.encode(),
        )
        assert response.status_code == 201
        yield test_client


def _model(monkeypatch, answer, quote):
    class MockModel:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def post(self, url, json):
            return httpx.Response(
                200,
                json={"message": {"content": __import__("json").dumps({
                    "supported": True, "answer": answer, "evidence_quote": quote
                })}, "done": True},
                request=httpx.Request("POST", url)
            )
    monkeypatch.setattr(rag.httpx, "AsyncClient", lambda **kwargs: MockModel())


def _ask(client):
    return client.post(
        "/api/rag/ask",
        headers={"X-KnowledgeAI-Workspace": "A" * 43},
        json={"question": "On which date will the workshop take place?"},
    ).json()


def test_api_repairs_unrelated_quote(client, monkeypatch):
    _model(monkeypatch, "15 December 2026", FEE_SENTENCE)
    result = _ask(client)
    assert result["status"] == "answered"
    assert result["answer"] == "15 December 2026"
    assert result["sources"][0]["evidence_quote"] == DATE_SENTENCE
    assert result["sources"][0]["source"] == "notes.txt"


def test_api_does_not_invent_date(client, monkeypatch):
    _model(monkeypatch, "16 December 2026", FEE_SENTENCE)
    result = _ask(client)
    assert result["status"] == "no_evidence"
    assert result["sources"] == []
