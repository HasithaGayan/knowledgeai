"""KnowledgeAI Day 71 - Local AI chat backend."""

from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

app = FastAPI(
    title="KnowledgeAI",
    version="0.1.0",
    description="Local AI chat API powered by Ollama.",
)

OLLAMA_URL = "http://127.0.0.1:11434"
MODEL = "qwen3:0.6b"

SYSTEM_PROMPT = (
    "You are KnowledgeAI, a helpful educational AI assistant. "
    "Give clear, accurate answers in simple English. "
    "Explain uncertainty instead of inventing facts. "
    "No documents are connected yet, so never claim "
    "to have read or searched a user's documents."
)


class HistoryMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=2000)
    history: list[HistoryMessage] = Field(
        default_factory=list,
        max_length=10,
    )


class ChatResponse(BaseModel):
    answer: str
    model: str


@app.get("/")
async def home():
    return {
        "application": "KnowledgeAI",
        "status": "ready",
        "documentation": "/docs",
    }


@app.get("/api/health")
async def health():
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{OLLAMA_URL}/api/tags"
            )
            response.raise_for_status()

        models = [
            item.get("name")
            for item in response.json().get("models", [])
        ]

        return {
            "status": "ready" if MODEL in models else "model_missing",
            "model": MODEL,
            "model_available": MODEL in models,
        }

    except (httpx.HTTPError, ValueError, KeyError):
        raise HTTPException(
            status_code=503,
            detail="Local Ollama server unavailable",
        )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):

    if not request.message.strip():
        raise HTTPException(
            status_code=422,
            detail="Message cannot be blank",
        )

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        }
    ]

    for item in request.history:
        if not item.content.strip():
            raise HTTPException(
                status_code=422,
                detail="History contains a blank message",
            )

        messages.append(item.model_dump())

    messages.append({
        "role": "user",
        "content": request.message.strip(),
    })

    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 256,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(
                f"{OLLAMA_URL}/api/chat",
                json=payload,
            )
            response.raise_for_status()

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Local AI response timed out",
        )

    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Cannot connect to Ollama",
        )

    except httpx.HTTPError:
        raise HTTPException(
            status_code=502,
            detail="Local AI provider request failed",
        )

    try:
        data = response.json()
        answer = data["message"]["content"]
    except (ValueError, KeyError, TypeError):
        raise HTTPException(
            status_code=502,
            detail="Invalid AI provider response",
        )

    if not isinstance(answer, str) or not answer.strip():
        raise HTTPException(
            status_code=502,
            detail="AI returned an empty answer",
        )

    return ChatResponse(
        answer=answer.strip(),
        model=MODEL,
    )

# KNOWLEDGEAI_DAY71_FRONTEND_ROUTE
from pathlib import Path as _KnowledgeAIPath
from fastapi.responses import FileResponse as _KnowledgeAIFileResponse


@app.get("/chat", include_in_schema=False)
async def knowledgeai_chat_page():
    """Serve the local KnowledgeAI chat UI on the same origin as the API."""
    page = _KnowledgeAIPath(__file__).resolve().parents[1] / "frontend" / "index.html"
    if not page.is_file():
        raise HTTPException(status_code=404, detail="KnowledgeAI frontend unavailable")
    return _KnowledgeAIFileResponse(page)

# KNOWLEDGEAI_DAY72_UPLOAD_ROUTE
from backend.document_upload import router as _knowledgeai_documents_router
app.include_router(_knowledgeai_documents_router)

# KNOWLEDGEAI_DAY72_STRUCTURED_ROUTE
from backend.structured_output import router as _knowledgeai_structured_router
app.include_router(_knowledgeai_structured_router)

# KNOWLEDGEAI_DAY73_TOOL_CALLING_ROUTE
from backend.tool_chat import router as _knowledgeai_day73_router
app.include_router(_knowledgeai_day73_router)

# KNOWLEDGEAI_DAY74_CONVERSATION_ROUTE
from backend.conversation_stream import router as _knowledgeai_day74_router
app.include_router(_knowledgeai_day74_router)
