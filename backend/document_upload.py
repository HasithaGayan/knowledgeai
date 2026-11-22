"""KnowledgeAI Day 72 — local-only, bounded document preview endpoints.

Files are processed in memory. No persistence, embeddings or RAG yet.
"""

from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from backend.document_ingestion import DocumentError, MAX_BYTES, ingest_document

router = APIRouter(tags=["documents"])
ROOT = Path(__file__).resolve().parents[1]


@router.get("/documents", include_in_schema=False)
async def document_page():
    """Serve the separate document-preview page without altering the chat UI."""
    page = ROOT / "frontend" / "documents.html"
    if not page.is_file():
        raise HTTPException(status_code=404, detail="Document page unavailable")
    return FileResponse(page, headers={"Cache-Control": "no-store"})


@router.post("/api/documents/preview")
async def preview_document(
    request: Request,
    x_filename: str | None = Header(default=None, alias="X-Filename"),
):
    """Accept one raw TXT/MD file (maximum 2 MB) for in-memory preview.

    Browser sends a File body with application/octet-stream and X-Filename.
    This is NOT multipart, so no new dependency or external service is used.
    """
    if x_filename is None:
        raise HTTPException(status_code=422, detail="X-Filename header is required")

    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type != "application/octet-stream":
        raise HTTPException(
            status_code=415,
            detail="Send raw file bytes as application/octet-stream",
        )

    # Read in bounded chunks so a dishonest Content-Length cannot bypass the limit.
    content = bytearray()
    async for fragment in request.stream():
        if len(content) + len(fragment) > MAX_BYTES:
            raise HTTPException(status_code=413, detail="File exceeds 2 MB limit")
        content.extend(fragment)

    try:
        chunks = ingest_document(x_filename, bytes(content))
    except DocumentError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return JSONResponse(
        {
            "filename": x_filename,
            "size_bytes": len(content),
            "chunk_count": len(chunks),
            "chunks": chunks,
            "stored_on_server": False,
            "document_qa_ready": False,
        },
        headers={"Cache-Control": "no-store"},
    )
