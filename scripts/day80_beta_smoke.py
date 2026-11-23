"""Local integration smoke check; no Ollama inference or personal document reads.

Run from repo root with: python -m scripts.day80_beta_smoke
"""
from __future__ import annotations
from fastapi.testclient import TestClient
from backend.app import app


ROUTES = (
    "/workspace", "/evaluation", "/api/beta/overview", "/chat", "/rag",
    "/conversations", "/tools", "/agent", "/privacy", "/documents", "/structured",
)


def run() -> None:
    with TestClient(app) as client:
        for route in ROUTES:
            response = client.get(route)
            if response.status_code != 200:
                raise RuntimeError(f"FAIL: {route} HTTP {response.status_code}")
            if "no-store" not in response.headers.get("cache-control", ""):
                raise RuntimeError(f"FAIL: {route} missing no-store")
            if response.headers.get("x-frame-options") != "DENY":
                raise RuntimeError(f"FAIL: {route} missing frame guard")
            print(f"PASS: {route}")
        overview = client.get("/api/beta/overview").json()
        if overview["evaluation"]["passed"] != 22 or overview["evaluation"]["total"] != 25:
            raise RuntimeError("Historical evaluation mismatch")
        print("PASS: synthetic evaluation metadata")
        print("PASS: no Ollama inference, private document reads or Git operations performed")


if __name__ == "__main__":
    run()
