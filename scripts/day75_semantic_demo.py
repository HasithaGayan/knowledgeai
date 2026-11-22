r"""Day 75 retrieval demo: evaluate 10 questions on tiny synthetic notes.

Run from the KnowledgeAI root:
    .\.venv\Scripts\python.exe scripts\day75_semantic_demo.py

This is a local similarity-search demonstration, NOT full RAG and NOT a
benchmark of real uploaded documents. Review every result manually.
"""

from __future__ import annotations

import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.semantic_retrieval import EmbeddingError, SemanticIndex

NOTES = [
    ("supervised", "supervised_learning.txt",
     "Supervised learning learns from examples paired with known labels. "
     "Classification predicts classes, whereas regression predicts numerical values."),
    ("unsupervised", "clustering.txt",
     "Unsupervised learning discovers patterns in data without target labels. "
     "Clustering groups similar examples using distance or similarity."),
    ("statistics", "hypothesis_testing.txt",
     "Hypothesis testing uses a null hypothesis, an alternative hypothesis, "
     "a significance level, and a test statistic to assess evidence."),
    ("sql", "database_queries.txt",
     "SQL SELECT retrieves data from relational tables. "
     "JOIN combines related tables and GROUP BY creates summary groups."),
    ("security", "web_security.txt",
     "A web API must validate inputs, enforce authorization, restrict access "
     "to users' data, and protect authentication credentials."),
    ("training", "model_evaluation.txt",
     "Machine learning models are evaluated on separate validation or test data. "
     "MAE measures average absolute prediction error and leakage can bias scores."),
]

EVALUATION = [
    ("How can a model learn from examples that already have the correct answers?", "supervised_learning.txt"),
    ("What is the difference between predicting categories and numbers?", "supervised_learning.txt"),
    ("What technique groups unlabeled examples by similarity?", "clustering.txt"),
    ("How do we discover data patterns when no target labels exist?", "clustering.txt"),
    ("What does a significance level mean in hypothesis testing?", "hypothesis_testing.txt"),
    ("How do I combine rows from two relational tables?", "database_queries.txt"),
    ("Which SQL clause summarizes records into groups?", "database_queries.txt"),
    ("How should an API protect private information?", "web_security.txt"),
    ("How is mean absolute error used to judge a predictive model?", "model_evaluation.txt"),
    ("Why must a machine learning test set be separate?", "model_evaluation.txt"),
]


def main() -> int:
    db_path = ROOT / "data" / "day75_semantic_demo.sqlite3"
    print("KNOWLEDGEAI DAY 75 — SEMANTIC SEARCH DEMO")
    print("Local Ollama model: all-minilm:latest")
    print("Corpus: 6 illustrative notes (not uploaded user files)")
    print("Indexed data: data/day75_semantic_demo.sqlite3 (Git ignored)")
    print()
    index = SemanticIndex(db_path)
    try:
        start = perf_counter()
        for doc_id, source, content in NOTES:
            index.index_chunks("day75_demo", doc_id, [{
                "source": source, "chunk_number": 1, "start": 0,
                "end": len(content), "text": content,
            }])
        print(f"Indexed {len(NOTES)} notes in {perf_counter()-start:.2f}s")
        top1 = 0
        for i, (query, expected_source) in enumerate(EVALUATION, start=1):
            started = perf_counter()
            results = index.search("day75_demo", query, top_k=3)
            if not results:
                raise RuntimeError("No search results for a populated test workspace")
            best = results[0]
            matched = best["source"] == expected_source
            top1 += int(matched)
            marker = "MATCH" if matched else "REVIEW"
            print(f"{i:2d}. [{marker}] score={best['score']:.3f} "
                  f"source={best['source']} ({perf_counter()-started:.2f}s)")
            print(f"    Question: {query}")
            print(f"    Expected: {expected_source}")
        print(f"\nTop-1 source match on these 10 illustrative cases: {top1}/10")
        print("REVIEW the matches and errors manually; a high score is not proof of truth.")
        print("Day 76 will connect retrieval to grounded AI answers and citations.")
        return 0
    except EmbeddingError as exc:
        print("Could not reach the local Ollama embedding service.")
        print("Make sure Ollama is running and all-minilm:latest is installed.")
        print(f"Details: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
