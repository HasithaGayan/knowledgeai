"""Day79 non-invasive local security smoke check; no server or Ollama needed."""
from __future__ import annotations

import subprocess
from fastapi.testclient import TestClient
from backend.app import app


def main():
    with TestClient(app) as client:
        checks = {
            "Privacy page": client.get("/privacy").status_code == 200,
            "Privacy JSON": client.get("/api/privacy/info").status_code == 200,
            "Host restriction": client.get("/", headers={"Host": "attacker.example"}).status_code == 403,
            "Cross-origin write restriction": client.post("/api/chat", headers={"Origin": "https://attacker.example"}, json={}).status_code == 403,
            "Oversized declared request": client.post("/api/chat", content=b"x" * (3 * 1024 * 1024 + 1)).status_code == 413,
            "No-store and anti-sniff headers": all(client.get("/").headers.get(k) == v for k, v in {
                "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY"
            }.items()),
        }
    tracked = subprocess.run(["git", "ls-files", "data/", "reports/generated/", ".venv/"], text=True, capture_output=True, check=True)
    checks["Private/generated directories not tracked"] = not bool(tracked.stdout.strip())
    for name, passed in checks.items():
        print(("PASS" if passed else "FAIL") + ": " + name)
    print("LIMITATION: This is a local smoke check; it does not prove production security or data encryption.")
    if not all(checks.values()):
        raise SystemExit("Day79 security smoke check failed")

if __name__ == "__main__":
    main()
