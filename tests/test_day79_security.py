"""Day 79 local security and privacy regression tests (no Ollama calls)."""
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.day79_security import LocalSecurityMiddleware, _origin_allowed, _host_only, local_client_allowed
from backend.day79_privacy import router as privacy_router


def app_factory(*, limit=60, exempt=True, max_size=3*1024*1024):
    app = FastAPI()

    @app.get("/")
    def home():
        return {"ok": True}

    @app.post("/api/chat")
    def chat():
        return {"ok": True}

    @app.post("/api/rag/ask")
    def rag():
        return {"ok": True}

    @app.post("/api/other")
    def other():
        return {"ok": True}

    app.add_middleware(LocalSecurityMiddleware, model_rate_limit=limit,
                       exempt_test_clients=exempt, max_declared_body_bytes=max_size)
    return TestClient(app)


def test_local_address_allowlist():
    for host in ("127.0.0.1", "::1", "testclient", "testserver"):
        assert local_client_allowed(host)


@pytest.mark.parametrize("bad", ["192.168.1.2", "10.0.0.1", "203.0.113.4", "", None, "127.0.0.1.evil.test"])
def test_rejects_remote_peer(bad):
    assert not local_client_allowed(bad)


@pytest.mark.parametrize("host,expected", [("127.0.0.1:8002", "127.0.0.1"), ("localhost:8002", "localhost"), ("[::1]:8002", "::1"), ("evil.example", "evil.example")])
def test_host_parser(host,expected):
    assert _host_only(host) == expected


def test_get_and_security_headers():
    response = app_factory().get("/")
    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "no-store" in response.headers["Cache-Control"]
    assert "camera=()" in response.headers["Permissions-Policy"]


def test_unexpected_host_rejected():
    response = app_factory().get("/", headers={"Host": "evil.example"})
    assert response.status_code == 403
    assert "no-store" in response.headers["Cache-Control"]


@pytest.mark.parametrize("origin", ["https://evil.example", "null", "http://testserver.evil.example", "http://testserver:8002", "http://localhost:8002"])
def test_cross_origin_write_rejected(origin):
    assert app_factory().post("/api/chat", headers={"Origin": origin}).status_code == 403


def test_exact_same_origin_accepted():
    assert app_factory().post("/api/chat", headers={"Origin": "http://testserver"}).status_code == 200


def test_no_origin_cli_accepted():
    assert app_factory().post("/api/chat").status_code == 200


def test_cross_site_fetch_metadata_rejected():
    assert app_factory().post("/api/chat", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403


def test_readonly_request_can_be_cross_origin_no_cors():
    response = app_factory().get("/", headers={"Origin": "https://evil.example"})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_declared_size_limit():
    assert app_factory(max_size=10).post("/api/chat", content=b"01234567890").status_code == 413
    assert app_factory(max_size=10).post("/api/chat", content=b"0123456789").status_code == 200


def test_rate_limit_for_ai_endpoints():
    client = app_factory(limit=2, exempt=False)
    assert client.post("/api/chat").status_code == 200
    assert client.post("/api/rag/ask").status_code == 200
    third = client.post("/api/chat")
    assert third.status_code == 429
    assert third.headers["Retry-After"] == "60"
    assert client.post("/api/other").status_code == 200


def test_get_does_not_consume_model_quota():
    client = app_factory(limit=1, exempt=False)
    for _ in range(4):
        assert client.get("/").status_code == 200
    assert client.post("/api/chat").status_code == 200
    assert client.post("/api/chat").status_code == 429


def test_test_client_exemption_preserves_regression_suite():
    client = app_factory(limit=1)
    for _ in range(4):
        assert client.post("/api/chat").status_code == 200


def test_origin_comparison_prevents_subdomain_spoof():
    assert _origin_allowed("http://127.0.0.1:8002", "127.0.0.1:8002")
    assert not _origin_allowed("http://127.0.0.1.attacker:8002", "127.0.0.1:8002")
    assert not _origin_allowed("http://127.0.0.1:9999", "127.0.0.1:8002")


def test_privacy_info_no_sensitive_values():
    app = FastAPI()
    app.include_router(privacy_router)
    client = TestClient(app)
    response = client.get("/api/privacy/info")
    assert response.status_code == 200
    payload = response.json()
    assert "not production" in payload["authentication"]
    assert "encryption" in payload
    assert "sensitive" in payload["warning"]


def test_privacy_page_file_available():
    page = Path(__file__).resolve().parents[1] / "frontend" / "privacy.html"
    assert page.is_file()
    contents = page.read_text(encoding="utf-8")
    assert "Privacy is part of the product" in contents
    assert "not real account authentication" in contents


def test_middleware_not_declared_production_authentication():
    from backend import day79_security
    assert "not production authentication" in day79_security.__doc__
