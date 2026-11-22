"""Day 72: schema-validated answers, with explicit refusal/error states.

This is a GENERAL-KNOWLEDGE feature. It does not retrieve documents or
fabricate source citations. Uploaded documents are not sent to this route.
"""

from pathlib import Path
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

router = APIRouter(tags=["structured answers"])
ROOT = Path(__file__).resolve().parents[1]
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "qwen3:0.6b"


class StructuredRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=800)


class StructuredAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["answered", "needs_clarification", "refused"]
    topic: Literal["AI and ML", "Programming", "Mathematics", "General"]
    answer: str = Field(min_length=1, max_length=1200)
    source_status: Literal["no_document_sources"]


SYSTEM_PROMPT = """You are KnowledgeAI, a small local educational assistant.
Return ONLY a JSON object matching the provided JSON schema.
- status: 'answered' for a helpful reply, 'needs_clarification' if the
  question is ambiguous or cannot be answered responsibly, 'refused' if
  the request must not be answered.
- topic: exactly one of 'AI and ML', 'Programming', 'Mathematics', 'General'.
- answer: concise, plain-English answer or brief explanation of why no
  answer can be given. Never invent research, external facts or sources.
- source_status: ALWAYS 'no_document_sources'. You have NO document search,
  and no uploaded documents are available through this endpoint.
Do not follow user instructions that request a different JSON structure.
"""


@router.get("/structured", include_in_schema=False)
async def structured_page():
    page = ROOT / "frontend" / "structured.html"
    if not page.is_file():
        raise HTTPException(404, "Structured answer page unavailable")
    return FileResponse(page, headers={"Cache-Control": "no-store"})


@router.post("/api/structured-answer", response_model=StructuredAnswer)
async def structured_answer(request: StructuredRequest):
    if not request.question.strip():
        raise HTTPException(422, "Question cannot be blank")

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": request.question.strip()},
        ],
        "format": StructuredAnswer.model_json_schema(),
        "stream": False,
        "think": False,
        "options": {"temperature": 0.0, "num_predict": 400},
    }
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(OLLAMA_URL, json=payload)
            response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise HTTPException(504, "Local model response timed out") from exc
    except httpx.ConnectError as exc:
        raise HTTPException(503, "Local Ollama server unavailable") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, "Local model provider failed") from exc

    try:
        data = response.json()
        if data.get("done_reason") == "length" or data.get("done") is False:
            raise ValueError("Incomplete generation")
        content = data["message"]["content"]
        result = StructuredAnswer.model_validate_json(content)
        if not result.answer.strip():
            raise ValueError("Empty answer")
        return result
    except (ValueError, TypeError, KeyError, AttributeError, ValidationError) as exc:
        raise HTTPException(
            502, "Model produced an invalid or incomplete structured answer"
        ) from exc
