"""Day 75 KnowledgeAI: local semantic chunk index + Ollama embeddings.

This is an isolated retrieval component. It does not change existing chat
routes, user accounts, or the document-upload UI. Only index trusted workspace
identifiers; never assume a client-provided workspace ID is authentication.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from contextlib import contextmanager
from typing import Iterator
from pathlib import Path
from typing import Callable, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

EMBEDDING_MODEL = "all-minilm:latest"
OLLAMA_EMBED_URL = "http://127.0.0.1:11434/api/embed"
_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
Vector = list[float]
Embedder = Callable[[Sequence[str]], list[Vector]]


class EmbeddingError(RuntimeError):
    """Ollama embedding unavailable or returned an invalid response."""


def _require_id(value: str, field: str) -> str:
    if not isinstance(value, str) or not _ID_PATTERN.fullmatch(value):
        raise ValueError(f"{field} must contain 1-64 letters, digits, _ or -")
    return value


def _checked_vectors(raw: object, count: int) -> list[Vector]:
    if not isinstance(raw, list) or len(raw) != count:
        raise ValueError("embedding count does not match input count")
    result: list[Vector] = []
    expected_dimensions: int | None = None
    for value in raw:
        if not isinstance(value, (list, tuple)) or not value:
            raise ValueError("embedding must be a non-empty numeric vector")
        if len(value) > 4096:
            raise ValueError("embedding has too many dimensions")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or
               not math.isfinite(v) for v in value):
            raise ValueError("embedding contains an invalid numeric value")
        vector = [float(v) for v in value]
        if math.sqrt(sum(v * v for v in vector)) == 0:
            raise ValueError("zero-length embedding is not useful for similarity")
        if expected_dimensions is None:
            expected_dimensions = len(vector)
        if len(vector) != expected_dimensions:
            raise ValueError("embedding dimensions differ")
        result.append(vector)
    return result


def ollama_embed(texts: Sequence[str], *, timeout: float = 60.0) -> list[Vector]:
    """Request embeddings from the local Ollama /api/embed endpoint.

    No secret, uploaded document or question is sent to a cloud service.
    """
    if not texts or len(texts) > 250 or any(
        not isinstance(t, str) or not t.strip() or len(t) > 4000 for t in texts
    ):
        raise ValueError("expected 1-250 nonempty texts of up to 4000 characters")
    body = json.dumps({"model": EMBEDDING_MODEL, "input": list(texts)}).encode("utf-8")
    request = Request(OLLAMA_EMBED_URL, data=body,
                      headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = json.load(response)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        raise EmbeddingError("Local Ollama embedding request failed") from exc
    if not isinstance(raw, dict):
        raise EmbeddingError("Ollama did not return a JSON object")
    try:
        return _checked_vectors(raw.get("embeddings"), len(texts))
    except ValueError as exc:
        raise EmbeddingError("Ollama returned unusable embeddings") from exc


def _cosine(a: Vector, b: Vector) -> float:
    if len(a) != len(b):
        raise ValueError("query and indexed embeddings have different dimensions")
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0 or mag_b == 0:
        raise ValueError("cannot compare zero-length embeddings")
    return max(-1.0, min(1.0, dot / (mag_a * mag_b)))


class SemanticIndex:
    """A small, local SQLite vector prototype (not a production vector DB).

    Workspace IDs are an isolation mechanism here; the public HTTP layer must
    separately authenticate and authorize callers before exposing this index.
    """

    def __init__(self, db_path: str | Path, *, embedder: Embedder = ollama_embed):
        self.path = Path(db_path)
        self.embedder = embedder
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS semantic_chunks (
                    workspace_id TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    chunk_number INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    start_position INTEGER NOT NULL,
                    end_position INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    model TEXT NOT NULL,
                    vector_json TEXT NOT NULL,
                    PRIMARY KEY (workspace_id, document_id, chunk_number)
                );
                CREATE INDEX IF NOT EXISTS idx_semantic_workspace
                    ON semantic_chunks(workspace_id, model);
            """)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Always close SQLite connections (including on Windows).

        Using ``with sqlite3.connect(...)`` alone only manages transactions;
        the connection stays open and can lock temporary database files.
        """
        conn = sqlite3.connect(str(self.path), timeout=10)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def index_chunks(self, workspace_id: str, document_id: str,
                     chunks: Sequence[dict]) -> int:
        """Replace one document's index atomically; preserve other documents."""
        _require_id(workspace_id, "workspace_id")
        _require_id(document_id, "document_id")
        if not isinstance(chunks, (list, tuple)) or not (1 <= len(chunks) <= 250):
            raise ValueError("index 1-250 chunks per document")

        validated: list[tuple[int, str, int, int, str]] = []
        seen: set[int] = set()
        for chunk in chunks:
            if not isinstance(chunk, dict):
                raise ValueError("each chunk must be a dictionary")
            number = chunk.get("chunk_number")
            source = chunk.get("source")
            start = chunk.get("start")
            end = chunk.get("end")
            content = chunk.get("text")
            if type(number) is not int or number < 1 or number in seen:
                raise ValueError("chunk_number must be a unique positive integer")
            if not isinstance(source, str) or not (1 <= len(source) <= 255) or \
                    any(ch in source for ch in ("/", "\\", "\x00")):
                raise ValueError("source must be a safe filename")
            if type(start) is not int or type(end) is not int or start < 0 or end <= start:
                raise ValueError("invalid chunk start/end positions")
            if not isinstance(content, str) or not content.strip() or len(content) > 4000:
                raise ValueError("each text chunk must have 1-4000 characters")
            seen.add(number)
            validated.append((number, source, start, end, content))

        vectors = _checked_vectors(self.embedder([c[-1] for c in validated]), len(validated))
        with self._connect() as conn:
            conn.execute("DELETE FROM semantic_chunks WHERE workspace_id = ? AND document_id = ?",
                         (workspace_id, document_id))
            conn.executemany("""
                INSERT INTO semantic_chunks
                (workspace_id, document_id, chunk_number, source,
                 start_position, end_position, text, model, vector_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [(workspace_id, document_id, num, src, start, end, txt,
                    EMBEDDING_MODEL, json.dumps(vec, separators=(",", ":")))
                   for (num, src, start, end, txt), vec in zip(validated, vectors)])
        return len(validated)

    def search(self, workspace_id: str, query: str, *, top_k: int = 3) -> list[dict]:
        """Return ranked chunks and scores. Scores are not answer guarantees."""
        _require_id(workspace_id, "workspace_id")
        if not isinstance(query, str) or not (1 <= len(query.strip()) <= 2000):
            raise ValueError("query must be 1-2000 non-whitespace characters")
        if type(top_k) is not int or not (1 <= top_k <= 20):
            raise ValueError("top_k must be 1-20")
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT document_id, chunk_number, source, start_position,
                       end_position, text, vector_json
                  FROM semantic_chunks
                 WHERE workspace_id = ? AND model = ?
            """, (workspace_id, EMBEDDING_MODEL)).fetchall()
        if not rows:
            return []
        qvec = _checked_vectors(self.embedder([query]), 1)[0]
        results = []
        for doc_id, number, source, start, end, content, raw_vector in rows:
            vec = _checked_vectors([json.loads(raw_vector)], 1)[0]
            score = _cosine(qvec, vec)
            results.append({"document_id": doc_id, "source": source,
                            "chunk_number": number, "start": start, "end": end,
                            "text": content, "score": round(score, 6)})
        results.sort(key=lambda x: (-x["score"], x["source"], x["chunk_number"]))
        return results[:top_k]

    def delete_document(self, workspace_id: str, document_id: str) -> int:
        _require_id(workspace_id, "workspace_id")
        _require_id(document_id, "document_id")
        with self._connect() as conn:
            cursor = conn.execute("""
                DELETE FROM semantic_chunks WHERE workspace_id = ? AND document_id = ?
            """, (workspace_id, document_id))
            return cursor.rowcount
