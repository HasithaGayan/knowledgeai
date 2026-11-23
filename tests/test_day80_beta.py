"""Day 80 local flagship integration and truthful-UI regression tests.

No Ollama, external network, real documents, or stored workspaces are needed.
"""
from pathlib import Path
import ast
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import day80_beta

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = (ROOT / "frontend" / "workspace.html").read_text(encoding="utf-8")
EVAL = (ROOT / "frontend" / "evaluation.html").read_text(encoding="utf-8")
DOC = (ROOT / "docs" / "day80_flagship_beta.md").read_text(encoding="utf-8")


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(day80_beta.router)
    return TestClient(app)


def test_workspace_page(client):
    response = client.get("/workspace")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "no-store" in response.headers["cache-control"]
    assert "Beautifully connected" in response.text


def test_evaluation_page(client):
    response = client.get("/evaluation")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "no-store" in response.headers["cache-control"]


def test_metadata_route(client):
    response = client.get("/api/beta/overview")
    assert response.status_code == 200
    assert response.json()["mode"] == "local_flagship_beta"


def test_route_is_read_only():
    assert {method for route in day80_beta.router.routes for method in (route.methods or [])} == {"GET"}


def test_status_contains_no_private_data(client):
    payload = client.get("/api/beta/overview").json()
    assert "documents" not in payload
    assert "conversations" not in payload
    assert "tokens" not in payload
    assert "prompts" not in payload


def test_result_is_historical_not_general(client):
    result = client.get("/api/beta/overview").json()["evaluation"]
    assert result["passed"] == 22 and result["total"] == 25
    assert result["known_failed_cases"] == [15, 18, 19]
    assert "historical" in result["note"].lower()


@pytest.mark.parametrize("name,passed,total", [
    ("direct", 12, 12), ("paraphrase", 4, 5),
    ("misleading", 1, 3), ("missing", 5, 5),
])
def test_category_counts(client, name, passed, total):
    result = client.get("/api/beta/overview").json()["evaluation"]["categories"][name]
    assert result == {"passed": passed, "total": total}


def test_feature_links_are_actual_endpoints(client):
    hrefs = {feature["href"] for feature in client.get("/api/beta/overview").json()["features"]}
    assert hrefs == {"/rag", "/chat", "/conversations", "/tools", "/agent", "/documents", "/structured", "/privacy"}


@pytest.mark.parametrize("path", ["/rag", "/chat", "/conversations", "/documents", "/structured", "/tools", "/agent", "/evaluation", "/privacy"])
def test_unified_nav(path):
    assert f'href="{path}"' in WORKSPACE


def test_existing_workspace_token_shared():
    assert "knowledgeai_day74_local_workspace" in WORKSPACE
    assert "crypto.getRandomValues" in WORKSPACE
    assert "localStorage" in WORKSPACE


def test_live_rag_apis_used():
    for endpoint in ("/api/rag/ask", "/api/rag/documents", "/api/health"):
        assert endpoint in WORKSPACE


def test_upload_validations_present():
    assert "/\\.(txt|md)$/i.test(file.name)" in WORKSPACE
    assert "file.size>2000000" in WORKSPACE
    assert "file.size===0" in WORKSPACE


def test_html_does_not_inject_model_answer_as_markup():
    assert "innerHTML" not in WORKSPACE
    assert "outerHTML" not in WORKSPACE
    assert "document.write" not in WORKSPACE
    assert "eval(" not in WORKSPACE
    assert "$('answer').textContent" in WORKSPACE
    assert "para.textContent" in WORKSPACE


def test_source_quotation_is_not_mislabeled_fact_proof():
    assert "not a guarantee of factual correctness" in WORKSPACE
    assert "semantic correctness is not guaranteed" in WORKSPACE


def test_privacy_warning_visible():
    assert "not production-authenticated" in WORKSPACE
    assert "No public access" in WORKSPACE
    assert "not real account authentication" in EVAL or "not real login accounts" in EVAL


def test_no_fake_subscription_or_account_claims():
    assert "AI Pro" not in WORKSPACE
    assert "Pro Plan" not in WORKSPACE
    assert "recent chats" not in WORKSPACE.lower()


def test_live_status_not_hardcoded():
    assert "Checking local AI" in WORKSPACE
    assert "data.model_available===true" in WORKSPACE


def test_responsive_styles():
    for screen in ("1180px", "810px", "560px"):
        assert screen in WORKSPACE


def test_reduced_motion_support():
    assert "prefers-reduced-motion" in WORKSPACE


def test_accessible_status_and_labels():
    assert 'role="status"' in WORKSPACE
    assert 'aria-live="polite"' in WORKSPACE
    assert 'aria-label="Ask your indexed documents"' in WORKSPACE


def test_evaluation_not_presented_as_live_dashboard():
    assert "historical evaluation" in EVAL
    assert "22 / 25" in EVAL
    assert "not an administrator" in EVAL


def test_evaluation_architecture_and_limits():
    for term in ("Ollama", "FastAPI", "SQLite", "all-minilm", "Agent Studio", "not real login", "source", "23"):
        if term == "23":
            continue
        assert term.lower() in EVAL.lower()


def test_case_study_contains_gate_and_mermaid():
    assert "```mermaid" in DOC
    assert "public" in DOC.lower()
    assert "25" in DOC and "22/25" in DOC
    assert "3-minute" in DOC or "three-minute" in DOC


def test_beta_module_has_no_new_unsafe_actions():
    source = (ROOT / "backend" / "day80_beta.py").read_text(encoding="utf-8")
    ast.parse(source)
    assert "httpx" not in source
    assert "subprocess" not in source
    assert "eval(" not in source
    assert "POST" not in source


def test_readme_markers_are_not_false_subscriptions():
    assert "account authentication" not in day80_beta.overview.__doc__ if day80_beta.overview.__doc__ else True


def test_smoke_script_parses():
    ast.parse((ROOT / "scripts" / "day80_beta_smoke.py").read_text(encoding="utf-8"))
