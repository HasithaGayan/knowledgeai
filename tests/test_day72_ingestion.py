"""Day 72 document ingestion tests."""

import pytest

from backend.document_ingestion import (
    DocumentError,
    ingest_document,
)


def test_short_document():
    chunks = ingest_document(
        "notes.txt",
        b"Artificial intelligence learns from data.",
    )

    assert len(chunks) == 1
    assert chunks[0]["source"] == "notes.txt"
    assert chunks[0]["chunk_number"] == 1
    assert "Artificial intelligence" in chunks[0]["text"]


@pytest.mark.parametrize(
    "filename",
    ["notes.txt", "lesson.md"],
)
def test_supported_extensions(filename):
    assert ingest_document(filename, b"Hello world")


def test_long_document_splits():
    content = ("machine learning uses data " * 100).encode()

    chunks = ingest_document(
        "ml.txt",
        content,
        chunk_size=300,
        overlap=40,
    )

    assert len(chunks) > 1
    assert all(len(c["text"]) <= 300 for c in chunks)
    assert chunks[1]["start"] < chunks[0]["end"]


def test_deterministic_results():
    content = b"Python is a programming language."

    first = ingest_document("python.txt", content)
    second = ingest_document("python.txt", content)

    assert first == second


def test_empty_document_rejected():
    with pytest.raises(DocumentError):
        ingest_document("empty.txt", b"")


def test_whitespace_only_rejected():
    with pytest.raises(DocumentError):
        ingest_document("blank.txt", b"   \n   ")


def test_pdf_not_yet_supported():
    with pytest.raises(DocumentError):
        ingest_document("notes.pdf", b"%PDF")


def test_path_traversal_rejected():
    with pytest.raises(DocumentError):
        ingest_document("../secret.txt", b"secret")


def test_windows_path_rejected():
    with pytest.raises(DocumentError):
        ingest_document("C:\\secret.txt", b"secret")


def test_oversized_document_rejected():
    with pytest.raises(DocumentError):
        ingest_document("big.txt", b"x" * 2_000_001)


def test_invalid_encoding_rejected():
    with pytest.raises(DocumentError):
        ingest_document("bad.txt", b"\xff\xfe")


def test_invalid_overlap_rejected():
    with pytest.raises(DocumentError):
        ingest_document(
            "test.txt",
            b"Hello",
            chunk_size=200,
            overlap=150,
        )
