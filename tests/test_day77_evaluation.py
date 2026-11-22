"""Fast, offline tests for Day 77's independent 25-case evaluation harness."""
from __future__ import annotations

from scripts.day77_evaluate_25 import CASES, DOCUMENTS, Case, score_case, validate_cases


def _answer(source: str, answer: str, quote: str):
    return {"status": "answered", "answer": answer,
            "sources": [{"source": source, "evidence_quote": quote}]}


def test_count_and_categories():
    validate_cases()
    assert len(CASES) == 25
    assert [sum(c.category == x for c in CASES) for x in ("direct", "paraphrase", "misleading", "missing")] == [12, 5, 3, 5]


def test_all_fixtures_fictional_and_distinct():
    assert len(DOCUMENTS) == 3
    assert all("FICTIONAL" in text for text in DOCUMENTS.values())


def test_correct_date_and_exact_citation():
    case = CASES[0]
    result = _answer("evaluation_workshop.txt", "15 December 2026", "The AI workshop will take place on 15 December 2026.")
    assert score_case(case, result)[0]


def test_answer_with_unrelated_quote_fails():
    case = CASES[0]
    result = _answer("evaluation_workshop.txt", "15 December 2026", "The workshop fee is LKR 2500.")
    assert not score_case(case, result)[0]


def test_invented_date_fails():
    case = CASES[0]
    result = _answer("evaluation_workshop.txt", "16 December 2026", "The AI workshop will take place on 15 December 2026.")
    assert not score_case(case, result)[0]


def test_fee_question_scored():
    case = CASES[1]
    assert score_case(case, _answer("evaluation_workshop.txt", "LKR 2500", "The workshop fee is LKR 2500."))[0]


def test_free_fee_contradiction_rejected_by_score():
    case = CASES[17]
    bad = _answer("evaluation_workshop.txt", "The workshop is free.", "The workshop fee is LKR 2500.")
    assert not score_case(case, bad)[0]


def test_correct_misleading_fee_answer_passes():
    case = CASES[17]
    good = _answer("evaluation_workshop.txt", "No, it is not free. The fee is LKR 2500.", "The workshop fee is LKR 2500.")
    assert score_case(case, good)[0]


def test_false_abstention_is_failed_positive():
    case = CASES[0]
    assert not score_case(case, {"status": "no_evidence", "answer": "Not found", "sources": []})[0]


def test_correct_missing_fact_abstention_passes():
    case = CASES[20]
    assert score_case(case, {"status": "no_evidence", "answer": "Not found", "sources": []})[0]


def test_invented_missing_fact_fails():
    case = CASES[20]
    assert not score_case(case, _answer("evaluation_workshop.txt", "Mr. Example", "The workshop fee is LKR 2500."))[0]


def test_wrong_document_or_fabricated_citation_fails():
    case = CASES[0]
    result = _answer("evaluation_policy.txt", "15 December 2026", "The workshop will take place on 15 December 2026.")
    assert not score_case(case, result)[0]
    result["sources"][0]["source"] = "evaluation_workshop.txt"
    assert not score_case(case, result)[0]
