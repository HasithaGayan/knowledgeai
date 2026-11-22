import json
import math
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.semantic_retrieval import (
    EmbeddingError, SemanticIndex, _checked_vectors, _cosine, ollama_embed,
)


class FakeEmbedder:
    def __init__(self):
        self.calls = 0

    def __call__(self, texts):
        self.calls += 1
        out = []
        for text in texts:
            lower = text.lower()
            if "math" in lower or "average" in lower:
                out.append([1.0, 0, 0])
            elif "sql" in lower or "database" in lower:
                out.append([0, 1.0, 0])
            else:
                out.append([0, 0, 1.0])
        return out


def make_chunk(content, source="notes.txt", number=1):
    return {"source": source, "chunk_number": number, "start": 0,
            "end": len(content), "text": content}


class IndexTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "vectors.sqlite3"
        self.embedder = FakeEmbedder()
        self.db = SemanticIndex(self.path, embedder=self.embedder)

    def test_connection_closes_after_context_exit(self):
        """Regression: Windows must be able to delete temp SQLite files."""
        with self.db._connect() as conn:
            self.assertEqual(conn.execute("SELECT 1").fetchone()[0], 1)
        with self.assertRaises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_index_and_search(self):
        self.db.index_chunks("owner1", "mathdoc", [make_chunk("Math average", "math.txt")])
        self.db.index_chunks("owner1", "sqldoc", [make_chunk("SQL database", "sql.txt")])
        rows = self.db.search("owner1", "average numbers", top_k=2)
        self.assertEqual(rows[0]["source"], "math.txt")
        self.assertEqual(rows[0]["score"], 1.0)
        self.assertEqual(rows[0]["chunk_number"], 1)

    def test_workspace_isolation(self):
        self.db.index_chunks("alice", "doc", [make_chunk("Math average")])
        self.assertEqual(self.db.search("bob", "math"), [])

    def test_workspace_id_validation(self):
        with self.assertRaises(ValueError):
            self.db.index_chunks("../alice", "doc", [make_chunk("Math average")])

    def test_document_id_validation(self):
        with self.assertRaises(ValueError):
            self.db.index_chunks("alice", "doc/../../etc", [make_chunk("Math average")])

    def test_reindex_replaces_old_chunks(self):
        self.db.index_chunks("alice", "doc", [make_chunk("Math average", "old.txt")])
        self.db.index_chunks("alice", "doc", [make_chunk("SQL database", "new.txt")])
        self.assertEqual(self.db.search("alice", "sql")[0]["source"], "new.txt")
        with self.db._connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM semantic_chunks").fetchone()[0], 1)

    def test_reindex_does_not_delete_other_doc(self):
        self.db.index_chunks("alice", "doc1", [make_chunk("Math average")])
        self.db.index_chunks("alice", "doc2", [make_chunk("SQL database")])
        self.db.index_chunks("alice", "doc1", [make_chunk("Math average revised")])
        self.assertEqual(len(self.db.search("alice", "sql", top_k=2)), 2)

    def test_delete_document_is_scoped(self):
        self.db.index_chunks("alice", "doc", [make_chunk("Math average")])
        self.db.index_chunks("bob", "doc", [make_chunk("SQL database")])
        self.assertEqual(self.db.delete_document("alice", "doc"), 1)
        self.assertEqual(self.db.search("alice", "math"), [])
        self.assertEqual(len(self.db.search("bob", "sql")), 1)

    def test_reopens_persisted_index(self):
        self.db.index_chunks("alice", "doc", [make_chunk("Math average")])
        new_index = SemanticIndex(self.path, embedder=FakeEmbedder())
        self.assertEqual(new_index.search("alice", "math")[0]["source"], "notes.txt")

    def test_reject_unsafe_source(self):
        with self.assertRaises(ValueError):
            self.db.index_chunks("alice", "doc", [make_chunk("Math average", "../a.txt")])

    def test_reject_duplicate_chunk_numbers(self):
        with self.assertRaises(ValueError):
            self.db.index_chunks("alice", "doc", [make_chunk("hello"), make_chunk("world")])

    def test_reject_empty_chunks(self):
        with self.assertRaises(ValueError):
            self.db.index_chunks("alice", "doc", [])

    def test_reject_invalid_positions(self):
        bad = make_chunk("Math average")
        bad["end"] = 0
        with self.assertRaises(ValueError):
            self.db.index_chunks("alice", "doc", [bad])

    def test_reject_blank_query(self):
        with self.assertRaises(ValueError):
            self.db.search("alice", " \t ")

    def test_reject_invalid_top_k(self):
        with self.assertRaises(ValueError):
            self.db.search("alice", "math", top_k=0)

    def test_empty_store_avoids_embedding(self):
        self.assertEqual(self.db.search("alice", "math"), [])
        self.assertEqual(self.embedder.calls, 0)

    def test_failed_embedding_preserves_old_document(self):
        self.db.index_chunks("alice", "doc", [make_chunk("Math average", "original.txt")])
        self.db.embedder = lambda texts: []
        with self.assertRaises(ValueError):
            self.db.index_chunks("alice", "doc", [make_chunk("SQL database", "replacement.txt")])
        self.db.embedder = FakeEmbedder()
        self.assertEqual(self.db.search("alice", "math")[0]["source"], "original.txt")

    def test_metadata_round_trip(self):
        self.db.index_chunks("alice", "doc", [make_chunk("Math average", "original.txt", 4)])
        row = self.db.search("alice", "math")[0]
        self.assertEqual((row["start"], row["end"], row["chunk_number"]), (0, 12, 4))

    def test_reject_dimension_mismatch(self):
        self.db.index_chunks("alice", "doc", [make_chunk("Math average")])
        self.db.embedder = lambda texts: [[1.0, 2.0]]
        with self.assertRaises(ValueError):
            self.db.search("alice", "math")

    def test_model_vector_validation(self):
        for val in ([[]], [[float("nan"), 1]], [[True, 1]], [[0, 0]]):
            with self.assertRaises(ValueError):
                _checked_vectors(val, 1)

    def test_cosine(self):
        self.assertEqual(_cosine([1.0, 0.0], [0.0, 1.0]), 0.0)
        self.assertEqual(_cosine([1.0, 0.0], [1.0, 0.0]), 1.0)

    def test_invalid_ollama_response(self):
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *_):
                pass
            def read(self, *args):
                return b'{"embeddings": []}'
        with patch("backend.semantic_retrieval.urlopen", return_value=Response()):
            with self.assertRaises(EmbeddingError):
                ollama_embed(["math"])


if __name__ == "__main__":
    unittest.main()
