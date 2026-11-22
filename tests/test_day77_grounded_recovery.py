"""Regression tests for seven observed Day 77 failures; no Ollama required."""
from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
import pytest

import backend.rag_assistant as rag
from backend.evidence_alignment import select_evidence_quote
from backend.grounded_recovery import recover_grounded_answer, complete_numeric_unit
from backend.semantic_retrieval import SemanticIndex
from scripts.day77_evaluate_25 import CASES, DOCUMENTS, score_case


def corpus():
    return [
        {"source": name, "text": text, "chunk_number": 1,
         "document_id": str(n + 1), "score": 0.4}
        for n, (name, text) in enumerate(DOCUMENTS.items())
    ]


@pytest.mark.parametrize("number", [15, 17, 18, 19, 20])
def test_recovers_expected_answer_and_exact_quote(number):
    case = CASES[number - 1]
    recovered = recover_grounded_answer(case.question, corpus())
    assert recovered is not None
    answer, p, quote = recovered
    payload = {"status": "answered", "answer": answer,
               "sources": [{"source": p["source"], "evidence_quote": quote}]}
    assert score_case(case, payload)[0], (number, payload)


def test_format_quote_aligned_with_correct_sentence():
    case = CASES[11]
    chosen = select_evidence_quote("PDF files", "Submit projects through the student portal.", corpus())
    assert chosen is not None
    p, quote = chosen
    assert score_case(case, {"status": "answered", "answer": "PDF files", "sources": [
        {"source": p["source"], "evidence_quote": quote}]})[0]


def test_bare_marks_completed_with_exact_context():
    case = CASES[9]
    quote = "Late submissions lose 5 marks per calendar day."
    answer = complete_numeric_unit(case.question, "5", quote)
    assert answer == "5 marks per calendar day"
    assert score_case(case, {"status": "answered", "answer": answer, "sources": [
        {"source": "evaluation_policy.txt", "evidence_quote": quote}]})[0]


def test_does_not_invent_units():
    assert complete_numeric_unit("How many marks per late day?", "5", "The fee is LKR 5") == "5"
    assert complete_numeric_unit("How many marks per late day?", "9", "Late loses 5 marks per day") == "9"


@pytest.mark.parametrize("question", [
    "What is the workshop instructor's name?",
    "What's the library wall color?",
    "What email receives late assignment appeals?",
    "Can I upload a 5 MB project?",  # maximum is NOT sufficient permission
    "Is the workshop free?",  # tested separately with a fee-free mock below
])
def test_fails_closed_for_missing_or_unsupported(question):
    if question == "Is the workshop free?":
        doc = {"text": "The event has no stated workshop fee.", "source": "x.txt", "chunk_number": 1, "document_id": "x", "score": 0.3}
        assert recover_grounded_answer(question, [doc]) is None
    else:
        assert recover_grounded_answer(question, corpus()) is None


def test_rejects_conflicting_retrieved_facts():
    passages = [
        {"text": "The library is located on Floor 2."},
        {"text": "The library is located on Floor 3."},
    ]
    assert recover_grounded_answer("Is the library on Floor 5?", passages) is None


def test_rejects_unsupported_format_citation():
    p = [{"source": "x.txt", "text": "Submit projects through the student portal."}]
    assert select_evidence_quote("PDF files", "Submit projects through the student portal.", p) is None


def test_invalid_llm_quote_fails_closed_even_when_number_in_file():
    assert select_evidence_quote("LKR 2500", "The workshop fee is USD 10.", corpus()) is None


@pytest.fixture
def client(monkeypatch, tmp_path):
    def indexed():
        return SemanticIndex(tmp_path / "vectors.db", embedder=lambda texts: [[1., 0., 0.] for _ in texts])
    monkeypatch.setattr(rag, "_index", indexed)
    app = FastAPI()
    app.include_router(rag.router)
    with TestClient(app) as cl:
        for filename, doc in DOCUMENTS.items():
            result = cl.post("/api/rag/documents", headers={
                "X-KnowledgeAI-Workspace": "A" * 43,
                "X-Filename": filename,
                "Content-Type": "application/octet-stream"
            }, content=doc.encode())
            assert result.status_code == 201
        yield cl


def fake_model(monkeypatch, **model):
    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def post(self, url, json):
            return httpx.Response(200, json={"message": {"content": __import__("json").dumps(model)}, "done": True},
                                  request=httpx.Request("POST", url))
    monkeypatch.setattr(rag.httpx, "AsyncClient", lambda **kwargs: Client())


def ask(client, question):
    result = client.post("/api/rag/ask", json={"question": question}, headers={
        "X-KnowledgeAI-Workspace": "A" * 43})
    assert result.status_code == 200
    return result.json()


@pytest.mark.parametrize("number", [15, 17, 18, 19, 20])
def test_api_recovers_llm_abstention(client, monkeypatch, number):
    case = CASES[number - 1]
    fake_model(monkeypatch, supported=False, answer="Not found in the provided documents.", evidence_quote="")
    payload = ask(client, case.question)
    assert score_case(case, payload)[0], (number, payload)


def test_api_repairs_wrong_file_format_citation(client, monkeypatch):
    fake_model(monkeypatch, supported=True, answer="PDF files", evidence_quote="Submit projects through the student portal.")
    case = CASES[11]
    assert score_case(case, ask(client, case.question))[0]


def test_api_completes_bare_numeric_mark_answer(client, monkeypatch):
    fake_model(monkeypatch, supported=True, answer="5", evidence_quote="Late submissions lose 5 marks per calendar day.")
    case = CASES[9]
    assert score_case(case, ask(client, case.question))[0]


def test_api_keeps_missing_answers_unanswered(client, monkeypatch):
    fake_model(monkeypatch, supported=False, answer="Not found in the provided documents.", evidence_quote="")
    for case in CASES[20:]:
        payload = ask(client, case.question)
        assert score_case(case, payload)[0], (case.number, payload)
