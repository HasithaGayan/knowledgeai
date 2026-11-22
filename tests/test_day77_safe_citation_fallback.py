"""Safe bad-citation fallback: original model claim must agree with recovered evidence."""
from __future__ import annotations

import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.rag_assistant as rag
from backend.safe_citation_fallback import agrees_with_recovered_evidence
from backend.semantic_retrieval import SemanticIndex
from scripts.day77_evaluate_25 import CASES, DOCUMENTS, score_case


@pytest.mark.parametrize('number,model_answer', [
    (15, 'The library opens at 9 AM on Saturday.'),
    (17, 'LKR 100 per day'),
    (18, 'No. The workshop fee is LKR 2500.'),
    (18, 'The workshop fee is LKR 2500.'),
    (19, 'No. The maximum upload size is 12 MB.'),
    (20, 'No, the library is located on Floor 2.'),
])
def test_agrees_with_corroborated_claim(number, model_answer):
    from backend.grounded_recovery import recover_grounded_answer
    case = CASES[number-1]
    passages = [{'source': name, 'text': content, 'chunk_number': 1,
                 'document_id': str(i), 'score': 0.5}
                for i, (name, content) in enumerate(DOCUMENTS.items())]
    recovered = recover_grounded_answer(case.question, passages)
    assert recovered is not None
    assert agrees_with_recovered_evidence(case.question, model_answer,
                                          recovered[0], recovered[2])


@pytest.mark.parametrize('number,bad_answer', [
    (15, 'The library opens at 8 AM on Saturday.'),
    (15, 'The library closes at 9 AM on Saturday.'),
    (15, 'The library opens at 9 AM and closes at 6 PM on Saturday.'),
    (17, 'The overdue charge is LKR 200 per day.'),
    (17, 'The fee is LKR 100 per month.'),
    (18, 'The AI workshop is free.'),
    (18, 'Yes, the workshop is free.'),
    (18, 'Yes.'),
    (18, 'No, the fee is LKR 1000.'),
    (19, 'Yes, a 20 MB project is allowed.'),
    (19, 'The maximum upload size is 20 MB.'),
    (19, 'No, maximum is 8 MB.'),
    (19, 'No, I can upload 20 MB.'),
    (20, 'Yes, the library is located on Floor 5.'),
    (20, 'No, it is on Floor 4.'),
    (20, 'The library is not on Floor 2.'),
    (20, 'No, the library is on Floor 2 and Floor 5.'),
    (18, 'Not found in the provided documents.'),
])
def test_rejects_contradictory_or_uninformative_model_claim(number, bad_answer):
    from backend.grounded_recovery import recover_grounded_answer
    case = CASES[number-1]
    passages = [{'source': name, 'text': content, 'chunk_number': 1,
                 'document_id': str(i), 'score': 0.5}
                for i, (name, content) in enumerate(DOCUMENTS.items())]
    recovered = recover_grounded_answer(case.question, passages)
    assert recovered is not None
    assert not agrees_with_recovered_evidence(case.question, bad_answer, recovered[0], recovered[2])


@pytest.mark.parametrize('q,a,recovered,quote', [
    ('What color are the walls?', 'Blue', 'Blue', 'Color: blue.'),
    ('Is the AI workshop free?', 'No', 'No. The workshop fee is LKR 2500.', ''),
    ('Can I upload 5 MB?', 'Yes', 'No. The maximum upload size is 12 MB.',
     'The maximum upload size is 12 MB.'),
])
def test_no_universal_fallback(q, a, recovered, quote):
    assert not agrees_with_recovered_evidence(q,a,recovered,quote)


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(rag, '_index', lambda: SemanticIndex(
        tmp_path / 'fake_vectors.sqlite3', embedder=lambda texts: [[1.,0.,0.] for _ in texts]))
    app = FastAPI()
    app.include_router(rag.router)
    with TestClient(app) as cli:
        for name, body in DOCUMENTS.items():
            res = cli.post('/api/rag/documents', headers={
                'X-KnowledgeAI-Workspace': 'A'*43, 'X-Filename': name,
                'Content-Type': 'application/octet-stream'}, content=body.encode('utf-8'))
            assert res.status_code == 201
        yield cli


def fake_model(monkeypatch, answer, proposed_quote, supported=True):
    class AI:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def post(self, url, json):
            return httpx.Response(200, json={'message': {'content': __import__('json').dumps({
                'supported': supported, 'answer': answer, 'evidence_quote': proposed_quote
            })}, 'done': True}, request=httpx.Request('POST', url))
    monkeypatch.setattr(rag.httpx, 'AsyncClient', lambda **kwargs: AI())


def ask(cli, question):
    res = cli.post('/api/rag/ask', headers={'X-KnowledgeAI-Workspace': 'A'*43}, json={'question': question})
    assert res.status_code == 200, res.text
    return res.json()


@pytest.mark.parametrize('number,answer,bad_quote', [
    (15, '9 AM', 'On weekdays the library opens at 8 AM and closes at 6 PM.'),
    (17, 'LKR 100 per day', 'Books may be borrowed for 14 days.'),
    (18, 'No. The workshop fee is LKR 2500.', 'The venue is Room B12.'),
    (19, 'No. The maximum upload size is 12 MB.', 'Submit projects through the student portal.'),
    (20, 'No. The library is located on Floor 2.', 'Membership requires a student ID card.'),
])
def test_integration_repairs_correct_claim_with_wrong_citation(client, monkeypatch, number, answer, bad_quote):
    fake_model(monkeypatch, answer, bad_quote)
    case = CASES[number-1]
    result = ask(client, case.question)
    assert score_case(case, result)[0], (number, result)


@pytest.mark.parametrize('number,bad_answer,bad_quote', [
    (15, '8 AM', 'The venue is Room B12.'),
    (17, 'LKR 200 per day', 'Books may be borrowed for 14 days.'),
    (18, 'The AI workshop is free.', 'The workshop fee is LKR 2500.'),
    (18, 'Yes', 'The venue is Room B12.'),
    (19, 'Yes, 20 MB is allowed.', 'The maximum upload size is 12 MB.'),
    (20, 'Yes, the library is on Floor 5.', 'The library is located on Floor 2.'),
])
def test_integration_never_rewrites_contradiction(client, monkeypatch, number, bad_answer, bad_quote):
    fake_model(monkeypatch, bad_answer, bad_quote)
    res = ask(client, CASES[number-1].question)
    assert res['status'] == 'no_evidence', res
    assert not res['sources']
