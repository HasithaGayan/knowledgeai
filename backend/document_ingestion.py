"""KnowledgeAI Day 72 - Safe text document ingestion."""

from hashlib import sha256
from pathlib import Path
import re

MAX_BYTES = 2_000_000
ALLOWED_EXTENSIONS = {".txt", ".md"}


class DocumentError(ValueError):
    """Raised when a document cannot be accepted."""


def ingest_document(
    filename: str,
    content: bytes,
    chunk_size: int = 800,
    overlap: int = 100,
) -> list[dict]:
    """Validate, decode and chunk one text document.

    Does not write files or send document content
    to any external service.
    """

    if not isinstance(filename, str):
        raise DocumentError("Invalid filename")

    if (
        not filename
        or filename.startswith(".")
        or "/" in filename
        or "\\" in filename
        or len(filename) > 120
        or "\x00" in filename
    ):
        raise DocumentError("Unsafe filename")

    if Path(filename).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise DocumentError("Unsupported file extension")

    if not isinstance(content, bytes):
        raise DocumentError("Content must be bytes")

    if not content:
        raise DocumentError("Document is empty")

    if len(content) > MAX_BYTES:
        raise DocumentError("Document exceeds size limit")

    if (
        not isinstance(chunk_size, int)
        or isinstance(chunk_size, bool)
        or chunk_size < 200
        or chunk_size > 4000
    ):
        raise DocumentError("Invalid chunk size")

    if (
        not isinstance(overlap, int)
        or isinstance(overlap, bool)
        or overlap < 0
        or overlap >= chunk_size // 2
    ):
        raise DocumentError("Invalid overlap")

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DocumentError(
            "Document must contain valid UTF-8 text"
        ) from exc

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.strip()

    if not text:
        raise DocumentError("Document has no readable text")

    document_hash = sha256(content).hexdigest()

    chunks = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))

        if end < len(text):
            middle = start + chunk_size // 2

            # Prefer ending near a word boundary.
            space = text.rfind(" ", middle, end)
            newline = text.rfind("\n", middle, end)
            boundary = max(space, newline)

            if boundary > start:
                end = boundary + 1

        piece = text[start:end].strip()

        if piece:
            chunks.append({
                "source": filename,
                "document_sha256": document_hash,
                "chunk_number": len(chunks) + 1,
                "start": start,
                "end": end,
                "text": piece,
            })

        if end >= len(text):
            break

        start = end - overlap

    return chunks
