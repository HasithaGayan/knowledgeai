"""KnowledgeAI Day 72: document upload page + local bounded byte API."""

import hashlib

from fastapi.testclient import TestClient

from backend.app import app
from backend.document_ingestion import MAX_BYTES


def send(filename: str, data: bytes, mime: str = "application/octet-stream"):
    with TestClient(app) as client:
        return client.post(
            "/api/documents/preview",
            headers={"X-Filename": filename, "Content-Type": mime},
            content=data,
        )


def test_document_page_served():
    with TestClient(app) as client:
        response = client.get("/documents")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "KnowledgeAI" in response.text
    assert 'id="upload-form"' in response.text


def test_text_upload_processed_in_memory():
    content = b"Supervised learning uses labeled examples."
    result = send("lesson.txt", content)
    assert result.status_code == 200
    data = result.json()
    assert data["filename"] == "lesson.txt"
    assert data["chunk_count"] == 1
    assert "labeled examples" in data["chunks"][0]["text"]
    assert data["chunks"][0]["document_sha256"] == hashlib.sha256(content).hexdigest()
    assert data["stored_on_server"] is False
    assert data["document_qa_ready"] is False
    assert result.headers["cache-control"] == "no-store"


def test_markdown_supported():
    result = send("notes.md", b"# Learning\n\nMachine learning uses data.")
    assert result.status_code == 200
    assert result.json()["chunk_count"] == 1


def test_long_text_produces_multiple_chunks():
    result = send("long.txt", b"Machine learning is useful. " * 110)
    assert result.status_code == 200
    assert result.json()["chunk_count"] >= 2


def test_pdf_rejected_until_supported():
    result = send("example.pdf", b"%PDF-1.7")
    assert result.status_code == 400


def test_traversal_filename_rejected():
    result = send("../secret.txt", b"secret")
    assert result.status_code == 400


def test_blank_file_rejected():
    result = send("empty.txt", b"   \n  ")
    assert result.status_code == 400


def test_invalid_utf8_rejected():
    result = send("bad.txt", b"\xff")
    assert result.status_code == 400


def test_oversized_file_rejected():
    result = send("large.txt", b"X" * (MAX_BYTES + 1))
    assert result.status_code == 413


def test_missing_filename_rejected():
    with TestClient(app) as client:
        response = client.post(
            "/api/documents/preview",
            content=b"Hello",
            headers={"Content-Type": "application/octet-stream"},
        )
    assert response.status_code == 422


def test_wrong_content_type_rejected():
    result = send("notes.txt", b"Hello", "text/plain")
    assert result.status_code == 415
