r"""Fast, offline KnowledgeAI latency sample; no model calls or user-data reads.

Usage: .\.venv\Scripts\python.exe scripts\day79_benchmark.py --requests 100
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import median
from time import perf_counter

from fastapi.testclient import TestClient
from backend.app import app


def percentile(sorted_values: list[float], fraction: float) -> float:
    index = int((len(sorted_values) - 1) * fraction)
    return round(sorted_values[index], 3)


def benchmark(requests: int) -> dict:
    # Lightweight, deterministic-enough, non-AI routes. This is NOT a load test.
    sample: dict[str, dict] = {}
    with TestClient(app) as client:
        for path in ("/", "/api/privacy/info", "/privacy"):
            times = []
            for _ in range(requests):
                t0 = perf_counter()
                response = client.get(path)
                elapsed = (perf_counter() - t0) * 1000
                if response.status_code != 200:
                    raise RuntimeError(f"Unexpected HTTP {response.status_code} from {path}")
                times.append(elapsed)
            times.sort()
            sample[path] = {
                "requests": requests,
                "median_ms": round(median(times), 3),
                "p95_ms": percentile(times, 0.95),
                "max_ms": round(times[-1], 3),
            }
    return {
        "run_utc": datetime.now(timezone.utc).isoformat(),
        "note": "Single-process local HTTP latency sample; no Ollama inference, security throughput, or production benchmark",
        "results": sample,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", type=int, default=100)
    args = parser.parse_args()
    if not 5 <= args.requests <= 1000:
        parser.error("--requests must be between 5 and 1000")
    report = benchmark(args.requests)
    folder = Path("reports/generated/day79")
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / ("latency_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".json")
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for endpoint, numbers in report["results"].items():
        print(f"{endpoint}: median {numbers['median_ms']}ms | p95 {numbers['p95_ms']}ms | max {numbers['max_ms']}ms")
    print("Local report:", target)
    print("No user prompts, uploaded documents, or API tokens were benchmarked.")


if __name__ == "__main__":
    main()
