"""Transparent privacy information for the local KnowledgeAI development app."""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(tags=["local privacy information"])


@router.get("/privacy", include_in_schema=False)
async def privacy_page():
    page = Path(__file__).resolve().parents[1] / "frontend" / "privacy.html"
    return FileResponse(page)


@router.get("/api/privacy/info")
async def privacy_info():
    return {
        "mode": "local prototype — not public multi-user hosting",
        "storage": "Local SQLite databases and approved Markdown reports under data/ by default",
        "ai_provider": "Local Ollama at 127.0.0.1; no hosted model required",
        "authentication": "Workspace tokens isolate prototype data but are not production login credentials",
        "retention": "Stored content may remain until explicitly deleted; deleting a browser token is not a data deletion operation",
        "encryption": "No application-level encryption at rest is guaranteed",
        "warning": "Do not upload sensitive documents or expose this server on the public internet",
    }
