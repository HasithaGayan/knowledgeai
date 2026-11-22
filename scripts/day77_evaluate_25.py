r"""KnowledgeAI Day 77: 25-case *real-model* evaluation, local-only.

Run from KnowledgeAI repository root after starting Uvicorn and Ollama:
    .\.venv\Scripts\python.exe scripts\day77_evaluate_25.py

Uses three clearly fictional synthetic notes in an isolated random workspace.
No live customer documents. No Git writes or model downloads. Results are
written to Git-ignored reports/generated/day77/. Failures are reported, not
silently changed into successful answers. This is an evaluation, NOT an
assertion that retrieval and RAG are safe or accurate for general use.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import secrets
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8002"
REPORT_DIR = Path("reports/generated/day77")

DOCUMENTS = {
    "evaluation_workshop.txt": (
        "FICTIONAL WORKSHOP FACT SHEET\n"
        "The AI workshop will take place on 15 December 2026.\n"
        "The workshop fee is LKR 2500.\n"
        "The venue is Room B12.\n"
        "The workshop covers Python and machine learning.\n"
        "Registration closes on 10 December 2026.\n"
        "The event is organized by Harbor Skills Lab.\n"
    ),
    "evaluation_policy.txt": (
        "FICTIONAL STUDENT SUBMISSION POLICY\n"
        "The project submission deadline is 20 January 2027.\n"
        "The maximum upload size is 12 MB.\n"
        "Submit projects through the student portal.\n"
        "Late submissions lose 5 marks per calendar day.\n"
        "Feedback is released within 7 working days.\n"
        "Assignments must be submitted as PDF files.\n"
    ),
    "evaluation_library.txt": (
        "FICTIONAL CAMPUS LIBRARY INFORMATION\n"
        "On weekdays the library opens at 8 AM and closes at 6 PM.\n"
        "On weekends the library opens at 9 AM and closes at 1 PM.\n"
        "Books may be borrowed for 14 days.\n"
        "The overdue fee is LKR 100 per day.\n"
        "The library is located on Floor 2.\n"
        "Membership requires a student ID card.\n"
    ),
}


@dataclass(frozen=True)
class Case:
    number: int
    category: str
    question: str
    expected_source: str | None
    answer_patterns: tuple[str, ...] = ()
    quote_pattern: str = ""


def c(num: int, category: str, question: str, source: str | None,
      *patterns: str, quote: str = "") -> Case:
    return Case(num, category, question, source, tuple(patterns), quote)


W = "evaluation_workshop.txt"
P = "evaluation_policy.txt"
L = "evaluation_library.txt"
CASES = (
    c(1, "direct", "On which date is the AI workshop?", W, r"15\s+December\s+2026", quote=r"15\s+December\s+2026"),
    c(2, "direct", "How much is the AI workshop fee?", W, r"(?:lkr\s*)?2[,]?500", quote=r"(?:lkr\s*)?2[,]?500"),
    c(3, "direct", "Where will the AI workshop take place?", W, r"Room\s+B12", quote=r"Room\s+B12"),
    c(4, "direct", "What topics does the AI workshop cover?", W, r"Python", r"machine\s+learning", quote=r"Python.*machine\s+learning"),
    c(5, "direct", "When does workshop registration close?", W, r"10\s+December\s+2026", quote=r"10\s+December\s+2026"),
    c(6, "direct", "Who organizes the AI workshop?", W, r"Harbor\s+Skills\s+Lab", quote=r"Harbor\s+Skills\s+Lab"),
    c(7, "direct", "What is the project submission deadline?", P, r"20\s+January\s+2027", quote=r"20\s+January\s+2027"),
    c(8, "direct", "What is the maximum upload size?", P, r"12\s*MB", quote=r"12\s*MB"),
    c(9, "direct", "Where should students submit projects?", P, r"student\s+portal", quote=r"student\s+portal"),
    c(10, "direct", "How many marks are lost per late day?", P, r"5\s+marks", quote=r"5\s+marks"),
    c(11, "direct", "When is feedback released?", P, r"7\s+working\s+days", quote=r"7\s+working\s+days"),
    c(12, "direct", "In what file format should assignments be submitted?", P, r"\bPDF\b", quote=r"PDF\s+files"),
    c(13, "paraphrase", "At what time can I enter the library on a weekday morning?", L, r"(?:8\s*(?:AM|A\.M\.)|08:00)", quote=r"8\s*AM"),
    c(14, "paraphrase", "When does the library shut on a normal workday?", L, r"(?:6\s*(?:PM|P\.M\.)|18:00)", quote=r"6\s*PM"),
    c(15, "paraphrase", "How early can I visit the library on Saturday?", L, r"(?:9\s*(?:AM|A\.M\.)|09:00)", quote=r"9\s*AM"),
    c(16, "paraphrase", "For how long may I keep a borrowed library book?", L, r"14\s+days", quote=r"14\s+days"),
    c(17, "paraphrase", "What's the daily overdue charge for a book?", L, r"(?:lkr\s*)?100", quote=r"LKR\s+100"),
    c(18, "misleading", "Is the AI workshop completely free?", W, r"(?:\bnot\s+free\b|\bpaid\b|\bno\b)", r"(?:lkr\s*)?2[,]?500", quote=r"LKR\s+2500"),
    c(19, "misleading", "Can I upload a 20 MB project because the policy allows it?", P, r"(?:\bno\b|not\s+allowed|exceeds|maximum|limit)", r"12\s*MB", quote=r"12\s*MB"),
    c(20, "misleading", "Is the library located on Floor 5?", L, r"(?:\bno\b|not\s+on|actually|instead)", r"Floor\s*2", quote=r"Floor\s*2"),
    c(21, "missing", "What is the workshop instructor's name?", None),
    c(22, "missing", "What is the Zoom meeting link for the workshop?", None),
    c(23, "missing", "Who is the library's head librarian?", None),
    c(24, "missing", "What email address receives late assignment appeals?", None),
    c(25, "missing", "What color are the library walls?", None),
)


def validate_cases() -> None:
    assert len(CASES) == 25 and [x.number for x in CASES] == list(range(1, 26))
    assert {x.category for x in CASES} == {"direct", "paraphrase", "misleading", "missing"}
    for x in CASES:
        if x.category == "missing":
            assert x.expected_source is None and not x.answer_patterns
        else:
            assert x.expected_source in DOCUMENTS and x.answer_patterns and x.quote_pattern


def normalized(text: str) -> str:
    return " ".join(text.split()).casefold()


def score_case(case: Case, payload: dict[str, Any]) -> tuple[bool, str]:
    """Strict observable scoring; literal quote present != full factual truth."""
    status = payload.get("status")
    sources = payload.get("sources")
    answer = payload.get("answer", "")
    if not isinstance(answer, str) or not isinstance(sources, list):
        return False, "invalid response shape"
    if case.category == "missing":
        if status == "no_evidence" and not sources:
            return True, "appropriate abstention"
        return False, "missing fact should have no answer and no citation"
    if status != "answered":
        return False, "false abstention or API error"
    if not all(re.search(pattern, answer, re.IGNORECASE) for pattern in case.answer_patterns):
        return False, "answer missing expected fact or correction"
    for source in sources:
        if not isinstance(source, dict) or source.get("source") != case.expected_source:
            continue
        quote = source.get("evidence_quote")
        if not isinstance(quote, str) or len(quote.strip()) < 8:
            continue
        document = DOCUMENTS[case.expected_source]
        if normalized(quote) not in normalized(document):
            continue
        if not re.search(case.quote_pattern, quote, re.IGNORECASE):
            continue
        return True, "answer and cited quote meet strict expected checks"
    return False, "missing, wrong, or unrelated source quote"


def api_call(method: str, path: str, token: str, *, body: bytes | None = None,
             filename: str | None = None, timeout: int = 210) -> dict[str, Any] | None:
    headers = {"X-KnowledgeAI-Workspace": token}
    if filename:
        headers["Content-Type"] = "application/octet-stream"
        headers["X-Filename"] = filename
    elif body is not None:
        headers["Content-Type"] = "application/json"
    req = Request(BASE + path, data=body, method=method, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except HTTPError as exc:
        details = exc.read(250).decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {exc.code}: {details}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Local KnowledgeAI server unavailable: {exc}") from exc


def run(*, limit: int, keep_workspace: bool) -> dict[str, Any]:
    validate_cases()
    if not 1 <= limit <= 25:
        raise ValueError("--limit must be from 1 to 25")
    token = secrets.token_urlsafe(32)
    indexed: list[str] = []
    results: list[dict[str, Any]] = []
    started = datetime.now(timezone.utc)
    print("Day 77 REAL model evaluation — fictional documents only")
    print("This measures observed behavior; a passing score is not a factual guarantee.")
    try:
        for filename, content in DOCUMENTS.items():
            print("Indexing", filename, flush=True)
            data = api_call("POST", "/api/rag/documents", token,
                            body=content.encode("utf-8"), filename=filename)
            if not isinstance(data, dict) or data.get("source") != filename:
                raise RuntimeError(f"Unexpected upload response for {filename}")
            indexed.append(str(data["document_id"]))
        for case in CASES[:limit]:
            since = time.perf_counter()
            payload: dict[str, Any]
            try:
                answer = api_call("POST", "/api/rag/ask", token,
                                  body=json.dumps({"question": case.question}).encode("utf-8"))
                if not isinstance(answer, dict):
                    raise RuntimeError("Missing JSON response")
                payload = answer
                passed, reason = score_case(case, payload)
            except Exception as exc:
                payload = {"status": "error", "answer": "", "sources": [],
                           "error": str(exc)}
                passed, reason = False, "API error"
            elapsed = round(time.perf_counter() - since, 2)
            results.append({"id": case.number, "category": case.category,
                            "question": case.question, "expected_source": case.expected_source,
                            "passed": passed, "reason": reason, "seconds": elapsed,
                            "response": payload})
            label = "PASS" if passed else "FAIL"
            print(f"{case.number:02d}/{limit:02d} [{label}] {case.category}: {case.question}", flush=True)
            if not passed:
                print("       Reason:", reason, "| Model:",
                      str(payload.get("answer", ""))[:180], flush=True)
    finally:
        if not keep_workspace:
            for document_id in indexed:
                try:
                    api_call("DELETE", f"/api/rag/documents/{document_id}", token)
                except Exception as exc:
                    print("WARNING: could not remove evaluation document:", exc,
                          file=sys.stderr)
    summary = {"total": len(results), "passed": sum(r["passed"] for r in results)}
    summary["failed"] = summary["total"] - summary["passed"]
    summary["accuracy_percent"] = round(summary["passed"] / summary["total"] * 100, 1) if summary["total"] else 0
    by_category = {}
    for category in sorted({r["category"] for r in results}):
        vals = [r for r in results if r["category"] == category]
        by_category[category] = {"passed": sum(x["passed"] for x in vals), "total": len(vals)}
    print("\nRESULT:", summary["passed"], "/", summary["total"],
          "passed (", summary["accuracy_percent"], "%)", sep="")
    print("By category:", by_category)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    filename = "day77_eval_" + started.strftime("%Y%m%d_%H%M%S_%f") + ".json"
    report = {"note": "Synthetic, small-sample local evaluation; not a production accuracy claim",
              "started_utc": started.isoformat(), "model": "qwen3:0.6b",
              "embedding_model": "all-minilm:latest", "cases_requested": limit,
              "summary": summary, "category_breakdown": by_category, "cases": results}
    location = REPORT_DIR / filename
    location.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Report:", location, "(Git-ignored)")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=25,
                        help="Run first N cases (3 for a quick smoke test; 25 full evaluation)")
    parser.add_argument("--keep-workspace", action="store_true",
                        help="Do not delete synthetic documents after evaluation (not recommended)")
    args = parser.parse_args()
    try:
        run(limit=args.limit, keep_workspace=args.keep_workspace)
    except (RuntimeError, ValueError, AssertionError) as exc:
        print("EVALUATION SETUP ERROR:", exc, file=sys.stderr)
        return 1
    return 0  # The evaluation reports failures; they are research findings, not script crashes.


if __name__ == "__main__":
    raise SystemExit(main())
