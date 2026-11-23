"""Regression checks for the shared KnowledgeAI presentation layer.

Only tests HTML, local routes, navigation, and preservation of live UI hooks.
Not a full visual accessibility audit or production readiness guarantee.
"""
from pathlib import Path
import re
import pytest
from fastapi.testclient import TestClient
from backend.app import app

ROOT = Path(__file__).resolve().parents[1]
PAGES = {
    "index.html": "/chat",
    "rag.html": "/rag",
    "documents.html": "/documents",
    "structured.html": "/structured",
    "tools.html": "/tools",
    "conversations.html": "/conversations",
    "agent.html": "/agent",
    "privacy.html": "/privacy",
    "evaluation.html": "/evaluation",
}

def source(name):
    return (ROOT / "frontend" / name).read_text(encoding="utf-8")

@pytest.mark.parametrize("name,route", PAGES.items())
def test_unified_theme_is_present_once(name, route):
    html = source(name)
    assert html.count('id="kai-unified-theme"') == 1
    assert html.count('id="kai-unified-sidebar"') == 1
    assert html.count('id="kai-mobile-trigger"') == 1
    assert html.count('id="kai-unified-script"') == 1
    assert 'class="kai-v2 kai-' in html
    assert 'aria-label="KnowledgeAI workspace navigation"' in html
    assert f'href="{route}" data-route="{route.lstrip("/")}"' in html
    assert 'KAI_UNIFIED_SHELL_START' in html
    assert 'KAI_UNIFIED_SHELL_END' in html

@pytest.mark.parametrize("name,route", PAGES.items())
def test_original_functional_hooks_remain(name, route):
    html = source(name)
    if name == "rag.html":
        for id_ in ('upload', 'indexBtn', 'question', 'askBtn', 'files', 'citation', 'answerText'):
            assert f'id="{id_}"' in html
    if name == "agent.html":
        for id_ in ('workflowForm', 'prepare', 'approve', 'reject', 'download', 'trace'):
            assert f'id="{id_}"' in html
    if name == "index.html":
        assert 'id="messages"' in html
    if name == "tools.html":
        assert '/api/tool-chat' in html
    assert html.count('<!doctype') + html.count('<!DOCTYPE') == 1

@pytest.mark.parametrize("route", PAGES.values())
def test_local_page_renders_shared_shell(route):
    client = TestClient(app)
    res = client.get(route)
    assert res.status_code == 200
    assert 'id="kai-unified-sidebar"' in res.text
    assert 'href="/workspace"' in res.text

def test_workspace_reference_design_untouched():
    html = source("workspace.html")
    assert 'Your knowledge.' in html
    assert 'Beautifully connected.' in html
    assert '<!-- KAI_UNIFIED_SHELL_START' not in html

def test_theme_keeps_local_prototype_notice():
    for name in ('rag.html', 'agent.html', 'privacy.html'):
        html = source(name).lower()
        assert ('local' in html or 'prototype' in html)
        assert 'not public hosting' in html

def test_theme_preserves_accessible_mobile_navigation():
    html = source('rag.html')
    assert 'aria-expanded="false"' in html
    assert 'aria-controls="kai-unified-sidebar"' in html
    assert "e.key==='Escape'" in html
    assert 'prefers-reduced-motion' in html


def test_no_training_day_labels_in_product_headings():
    for page, original in (
        ('tools.html','Day 73 · Tool calling'),
        ('conversations.html','DAY 74 · CONVERSATION STUDIO'),
        ('documents.html','Day 72 · Document processing'),
        ('structured.html','Day 72 · Structured AI outputs'),
        ('index.html','KnowledgeAI · v0.1 · Day 71'),
    ):
        assert original not in source(page)
