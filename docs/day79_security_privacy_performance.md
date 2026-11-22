# KnowledgeAI — Day 79 security, privacy and performance review

## Scope
Local-only development prototype, based on the Day 78 Agent Studio version.
Day 79 adds restrictive HTTP middleware, transparent privacy information,
regression checks, a lightweight latency sampler, and local security smoke checks.

## Implemented safeguards
- Requests from non-loopback peers or unexpected Host values are rejected.
- Cross-origin mutation attempts are rejected using Origin and Fetch Metadata.
- Response headers include `Cache-Control: no-store`, `X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy`, and a restrictive `Permissions-Policy`.
- Excessively large *declared* request bodies are rejected (3 MiB).
- Local expensive AI POST paths are bounded by an in-memory per-peer burst counter.
- Existing document and workspace validation remain in place.
- No raw prompts, workspace tokens, document text or user PII are logged by middleware.
- `GET /privacy` and `GET /api/privacy/info` disclose important limitations.

## Test commands
Run the full suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Local security checks:

```powershell
.\.venv\Scripts\python.exe scripts\day79_security_check.py
```

Local non-model latency sample:

```powershell
.\.venv\Scripts\python.exe scripts\day79_benchmark.py --requests 100
```

The generated latency JSON stays under the Git-ignored
`reports/generated/day79/` directory. Results measure only lightweight HTTP
paths on this laptop, not inference latency or internet-scale load.

## Remaining production blockers
- Workspace tokens are not real identity authentication or production RBAC.
- There is no guaranteed encryption at rest, key rotation, or multi-user audit trail.
- A Content-Length check is not a complete streamed-body size limit.
- In-memory rate limits reset at restart and are not distributed.
- Browser security is not comprehensively covered by a strict CSP.
- Uploaded text is not an isolated sandbox. Prompt injection remains possible.
- Security headers and loopback-only access are NOT a substitute for reverse
  proxy, TLS, authentication, session management or deployment review.
- Dependencies and vulnerabilities require a maintained audit process.
- The app must remain bound to `127.0.0.1` until proper public security is built.

**Day 79 is not a certification of security or production readiness.**
