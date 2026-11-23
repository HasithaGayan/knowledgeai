"""KnowledgeAI local flagship beta: unified workspace and transparent evaluation.

This router adds no public account system, network permissions, background AI
calls, or new persistent user storage. Existing Day79 local middleware applies.
"""
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

router = APIRouter(tags=["local flagship beta"])
ROOT = Path(__file__).resolve().parents[1]
_LOCAL = frozenset({"127.0.0.1", "::1", "testclient", "testserver"})

_FEATURES = (
    {"name": "Document Q&A", "href": "/rag", "purpose": "Question answering with retrieved source quotations"},
    {"name": "AI Chat", "href": "/chat", "purpose": "Local conversational assistance"},
    {"name": "Conversations", "href": "/conversations", "purpose": "Locally stored conversation history"},
    {"name": "Safe tools", "href": "/tools", "purpose": "Bounded text and numeric tools"},
    {"name": "Agent Studio", "href": "/agent", "purpose": "Approval-gated local report workflow"},
    {"name": "Document Studio", "href": "/documents", "purpose": "TXT/Markdown document preview"},
    {"name": "Structured answers", "href": "/structured", "purpose": "Schema-constrained local model output"},
    {"name": "Privacy Center", "href": "/privacy", "purpose": "Local prototype privacy limitations"},
)


def _local(request: Request) -> None:
    if request.client is None or request.client.host not in _LOCAL:
        raise HTTPException(status_code=403, detail="Local KnowledgeAI only")


def _page(name: str, request: Request) -> FileResponse:
    _local(request)
    path = ROOT / "frontend" / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Workspace page unavailable")
    return FileResponse(path, headers={"Cache-Control": "no-store"})


@router.get("/workspace", include_in_schema=False)
async def workspace_page(request: Request):
    return _page("workspace.html", request)


@router.get("/evaluation", include_in_schema=False)
async def evaluation_page(request: Request):
    return _page("evaluation.html", request)


@router.get("/api/beta/overview")
async def overview(request: Request):
    """Public-to-this-local-browser metadata ONLY. No private documents, tokens, chats."""
    _local(request)
    return {
        "product": "KnowledgeAI",
        "mode": "local_flagship_beta",
        "primary_use": "source-supported document question answering",
        "features": list(_FEATURES),
        "evaluation": {
            "dataset": "25 synthetic questions over 3 fictional documents",
            "passed": 22,
            "total": 25,
            "observed_date": "2026-11-22",
            "categories": {
                "direct": {"passed": 12, "total": 12},
                "paraphrase": {"passed": 4, "total": 5},
                "misleading": {"passed": 1, "total": 3},
                "missing": {"passed": 5, "total": 5},
            },
            "known_failed_cases": [15, 18, 19],
            "note": "Historical synthetic-run result, not a live or general accuracy guarantee",
        },
        "limitations": [
            "Workspace tokens are not real account authentication",
            "The local prototype is not approved for public internet access",
            "Source quote checks are not general semantic fact verification",
            "Local databases are not guaranteed encrypted at rest",
        ],
    }
