# KnowledgeAI · Agent Studio

## Goal

An inspect → calculate → draft → review → save workflow controlled by server-side permissions. This is deliberately bounded orchestration, not an autonomous general-purpose agent.

## How to use

1. Start the local server: `python -m uvicorn backend.app:app --host 127.0.0.1 --port 8002`.
2. Open `http://127.0.0.1:8002/agent`.
3. Enter text and optionally numbers; click **Prepare review**.
4. Examine the local AI draft and the execution trace.
5. Choose **Approve & save report** or **Reject — do not save**.
6. Only an explicitly approved workflow writes a Markdown report to the local, Git-ignored `data/agent_reports/` directory. Download it through the workspace-scoped endpoint.

## Safety properties

- Application, not LLM, chooses and runs tools. Only `inspect_text` and `calculate_average` are available; no arbitrary command execution, file reading or external service actions.
- A human approval request is a separate required HTTP operation; drafting itself never writes a report.
- Plans have at most six known steps; there is no open-ended tool recursion or self-modifying behavior.
- Workspace token digests scope workflows; plaintext tokens are never stored. Same-origin local browser access is intended, but this is **not public user authentication**.
- Expiry is 60 minutes, approval is once-only, and report paths are server-generated and isolated per workspace.
- Reports are Markdown, not executable programs. No user-defined filesystem paths are accepted.
- Trace stores step names, status, durations, counts and outcomes—not raw notes, tokens or full provider prompts.
- Unavailable or malformed local Ollama replies produce a visibly labeled, metrics-only fallback, not a fabricated AI summary.
- The local model's summary is **not verified against external evidence**, and can make mistakes. Human review is mandatory.

## Retention and limitations

- Local SQLite stores the drafted summary, trace, title, and approval status before approval so the user can review and decide.
- Raw text is sent to a local Ollama instance for summary but is not copied into structured trace fields. Sensitive notes should not be entered until Day 79 privacy/security hardening is complete.
- This local demo is not production authentication, distributed orchestration, multi-tenant hosting, durable job queue, or external side-effect approval system.
- No automatic deployment, Git submission, or external API integration is included.
- The workflow uses one bounded LLM drafting step; actual tool use remains deterministic and verifiable.

## Verification

Run `python -m pytest -q`. The new Day 78 tests validate non-approved runs, explicit approvals, rejected approvals, cross-workspace isolation, input limits, replay protection, expiry, tracing, download permissions, and fallback behavior.

Manual check: prepare and reject one workflow (no report created); prepare and approve a second workflow (download report), and inspect trace statuses.
