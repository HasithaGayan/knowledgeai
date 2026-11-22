"""Day 79: local-prototype HTTP protections (not production authentication).

Fail closed for remote peers and unexpected Host/Origin, add privacy headers,
limit declared request size and bound bursts of costly AI endpoints.
This is deliberately *not* a reverse-proxy, authentication, WAF or streaming
body-size enforcement substitute. Only serve via 127.0.0.1.
"""
from __future__ import annotations

from collections import defaultdict, deque
from threading import Lock
from time import monotonic
from urllib.parse import urlsplit

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse

_ALLOWED_CLIENTS = frozenset({"127.0.0.1", "::1", "testclient", "testserver"})
_ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "testserver", "testclient"})
_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_AI_PATHS = frozenset({"/api/chat", "/api/rag/ask", "/api/tool-chat", "/api/agent/workflows"})


def local_client_allowed(host: str | None) -> bool:
    return host in _ALLOWED_CLIENTS


def _host_only(host_header: str) -> str:
    value = host_header.strip().lower()
    if value.startswith("["):
        return value[1:].split("]", 1)[0] if "]" in value else ""
    return value.split(":", 1)[0]


def _origin_allowed(origin: str | None, host: str) -> bool:
    if origin is None:
        return True  # PowerShell / direct local API clients do not send Origin.
    try:
        parsed = urlsplit(origin)
        # Require exact authority, not merely the same hostname. No 'null'.
        return parsed.scheme in {"http", "https"} and parsed.netloc.lower() == host.lower() and not parsed.path and not parsed.query and not parsed.fragment
    except ValueError:
        return False


class LocalSecurityMiddleware:
    """Minimal ASGI middleware; no request body inspection or private-data logging."""

    def __init__(self, app, *, max_declared_body_bytes: int = 3 * 1024 * 1024,
                 model_rate_limit: int = 60, window_seconds: int = 60,
                 exempt_test_clients: bool = True):
        self.app = app
        self.max_declared_body_bytes = max_declared_body_bytes
        self.model_rate_limit = model_rate_limit
        self.window_seconds = window_seconds
        self.exempt_test_clients = exempt_test_clients
        self._counts = defaultdict(deque)
        self._lock = Lock()

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)

        headers = Headers(scope=scope)
        client = scope.get("client")
        peer = client[0] if client else None
        host = headers.get("host", "")
        method = scope.get("method", "GET").upper()
        path = scope.get("path", "")

        async def deny(status: int, message: str, extra: dict | None = None):
            response = JSONResponse({"detail": message}, status_code=status, headers=extra or {})
            await response(scope, receive, secure_send)

        async def secure_send(message):
            if message["type"] == "http.response.start":
                h = MutableHeaders(scope=message)
                h["X-Content-Type-Options"] = "nosniff"
                h["X-Frame-Options"] = "DENY"
                h["Referrer-Policy"] = "no-referrer"
                h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
                h["Cache-Control"] = "no-store"
            await send(message)

        if not local_client_allowed(peer) or _host_only(host) not in _ALLOWED_HOSTS:
            return await deny(403, "Local KnowledgeAI access only")

        if method in _WRITE_METHODS:
            if not _origin_allowed(headers.get("origin"), host):
                return await deny(403, "Cross-origin modification blocked")
            if headers.get("sec-fetch-site", "").lower() == "cross-site":
                return await deny(403, "Cross-site modification blocked")

            length = headers.get("content-length")
            if length is not None:
                if not length.isdecimal():
                    return await deny(400, "Invalid Content-Length")
                if int(length) > self.max_declared_body_bytes:
                    return await deny(413, "Declared request body too large")

            # Local resource protection; not distributed or production-grade.
            if (path in _AI_PATHS or (path.startswith("/api/conversations/") and path.endswith("/stream"))):
                if not (self.exempt_test_clients and peer in {"testclient", "testserver"}):
                    now = monotonic()
                    with self._lock:
                        q = self._counts[peer]
                        while q and q[0] <= now - self.window_seconds:
                            q.popleft()
                        if len(q) >= self.model_rate_limit:
                            return await deny(429, "Local AI request rate limit reached", {"Retry-After": str(self.window_seconds)})
                        q.append(now)

        await self.app(scope, receive, secure_send)
