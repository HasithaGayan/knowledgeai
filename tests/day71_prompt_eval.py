"""Day 71: Evaluate 10 real KnowledgeAI model responses."""

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/generated/day71/prompt_results.json"
API = "http://127.0.0.1:8001"

CASES = [
    {
        "name": "AI terminology",
        "prompt": "What does AI stand for?",
        "pattern": r"artificial intelligence",
    },
    {
        "name": "API terminology",
        "prompt": "What does API stand for?",
        "pattern": r"application programming interface",
    },
    {
        "name": "SQL terminology",
        "prompt": "What does SQL stand for?",
        "pattern": r"structured query language",
    },
    {
        "name": "Arithmetic",
        "prompt": "What is 7 + 5? Answer with only the number.",
        "pattern": r"\b12\b",
    },
    {
        "name": "Machine learning",
        "prompt": "Explain machine learning in one simple sentence.",
        "pattern": r"\bdata\b|\bexamples\b",
    },
    {
        "name": "Supervised learning",
        "prompt": "Explain supervised learning briefly.",
        "pattern": r"labelled|labeled|known output|input.*output",
    },
    {
        "name": "Python programming",
        "prompt": "What is a Python list?",
        "pattern": r"items|elements|collection|values",
    },
    {
        "name": "Git fundamentals",
        "prompt": "What does a Git commit do?",
        "pattern": r"save|saves|saved|record|snapshot|version",
    },
    {
        "name": "RAG terminology",
        "prompt": "What does RAG stand for in AI?",
        "pattern": r"retrieval.augmented generation",
    },
    {
        "name": "Document honesty",
        "prompt": (
            "Are my private documents connected to "
            "this KnowledgeAI app right now? "
            "Answer honestly."
        ),
        "pattern": r"\bno\b|\bnot\b|cannot|can't|aren't",
    },
]


def main():
    results = []
    errors = 0

    with httpx.Client(timeout=180) as client:
        health = client.get(f"{API}/api/health")
        health.raise_for_status()

        if not health.json().get("model_available"):
            raise RuntimeError("Local AI model unavailable")

        for index, case in enumerate(CASES, start=1):
            print(f"\n[{index}/10] {case['name']}")

            start = time.perf_counter()

            record = {
                "name": case["name"],
                "prompt": case["prompt"],
                "expected_pattern": case["pattern"],
            }

            try:
                response = client.post(
                    f"{API}/api/chat",
                    json={
                        "message": case["prompt"],
                        "history": [],
                    },
                )
                response.raise_for_status()

                data = response.json()
                answer = data["answer"]

                if not isinstance(answer, str) or not answer.strip():
                    raise ValueError("Empty AI response")

                match = bool(
                    re.search(
                        case["pattern"],
                        answer,
                        flags=re.IGNORECASE,
                    )
                )

                record.update({
                    "model": data["model"],
                    "answer": answer,
                    "keyword_match": match,
                    "request_success": True,
                })

                print("Answer:", answer[:220])
                print(
                    "Keyword check:",
                    "MATCH" if match else "REVIEW",
                )

            except (
                httpx.HTTPError,
                ValueError,
                KeyError,
                TypeError,
            ) as exc:
                errors += 1
                record.update({
                    "request_success": False,
                    "keyword_match": False,
                    "error": str(exc),
                })
                print("REQUEST FAILED:", exc)

            record["seconds"] = round(
                time.perf_counter() - start, 2
            )
            results.append(record)

    matches = sum(
        item["keyword_match"] for item in results
    )

    report = {
        "date_utc": datetime.now(timezone.utc).isoformat(),
        "model": "qwen3:0.6b",
        "total_prompts": len(CASES),
        "successful_requests": len(CASES) - errors,
        "keyword_matches": matches,
        "manual_review_required": len(CASES) - matches,
        "note": (
            "Keyword checks are heuristic, not a "
            "substitute for human factual evaluation. "
            "Model responses may vary between runs."
        ),
        "results": results,
    }

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n=== KNOWLEDGEAI DAY 71 EVALUATION ===")
    print("Prompts executed:", len(results))
    print("Successful API requests:", len(results) - errors)
    print("Keyword matches:", matches, "/ 10")
    print("Manual review flags:", len(results) - matches)
    print("Saved report:", REPORT)

    if errors:
        raise SystemExit(
            "Some requests failed. Inspect the saved report."
        )

    print("KNOWLEDGEAI 10 LIVE PROMPTS EXECUTED")


if __name__ == "__main__":
    main()
