"""Day 73: bounded, application-controlled Ollama function calling.

This is an independent router: the existing /api/chat and pages are unchanged.
"""

import json
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field

from backend.safe_tools import ToolExecutionError, run_tool, tool_definitions

router = APIRouter()
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "qwen3:0.6b"
SYSTEM = (
    "You are KnowledgeAI's local tool assistant. When the user asks for an "
    "arithmetic average, call calculate_average with the given numeric values. "
    "When asked to count words, lines or characters in supplied text, call "
    "inspect_text. Never invent a tool result or claim you used a tool if "
    "no tool was called. These are the only available tools. "
    "Only the backend is allowed to execute tools. "
    "Do not claim access to private documents, files, or the internet."
)


class HistoryMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class ToolChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=2000)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=10)


class ToolChatResponse(BaseModel):
    answer: str
    model: str
    tools_used: list[dict]


async def call_model(payload: dict) -> dict:
    """Call only the local Ollama endpoint; sanitize provider exceptions."""
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(OLLAMA_URL, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException as exc:
        raise HTTPException(504, "Local AI request timed out") from exc
    except httpx.ConnectError as exc:
        raise HTTPException(503, "Ollama is not running") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, "Local AI provider returned an error") from exc
    if not isinstance(data, dict) or not isinstance(data.get("message"), dict):
        raise HTTPException(502, "Invalid AI provider response")
    return data["message"]


@router.post("/api/tool-chat", response_model=ToolChatResponse)
async def tool_chat(request: ToolChatRequest):
    if not request.message.strip() or any(not h.content.strip() for h in request.history):
        raise HTTPException(422, "Blank messages are not allowed")

    messages: list[dict] = [{"role": "system", "content": SYSTEM}]
    messages.extend(h.model_dump() for h in request.history)
    messages.append({"role": "user", "content": request.message.strip()})

    first = await call_model({
        "model": MODEL,
        "messages": messages,
        "tools": tool_definitions(),
        "stream": False,
        "think": False,
        "options": {"temperature": 0, "num_predict": 250},
    })
    calls = first.get("tool_calls") or []
    if not isinstance(calls, list) or len(calls) > 2:
        raise HTTPException(502, "AI requested too many or invalid tools")

    if not calls:
        answer = first.get("content")
        if not isinstance(answer, str) or not answer.strip():
            raise HTTPException(502, "AI returned no answer")
        return ToolChatResponse(answer=answer.strip(), model=MODEL, tools_used=[])

    used = []
    authorized_calls = []
    # Authorization happens before any tool executes.
    for call in calls:
        if not isinstance(call, dict) or not isinstance(call.get("function"), dict):
            raise HTTPException(502, "Malformed AI tool request")
        function = call["function"]
        name, arguments = function.get("name"), function.get("arguments")
        if not isinstance(name, str) or not isinstance(arguments, dict):
            raise HTTPException(502, "Malformed AI tool arguments")
        if name not in {"calculate_average", "inspect_text"}:
            raise HTTPException(403, "Tool not permitted")
        authorized_calls.append({"name": name, "arguments": arguments})

    verified_calls = []
    # run_tool enforces value bounds; both tools are read-only and side-effect-free.
    for entry in authorized_calls:
        try:
            result = run_tool(entry["name"], entry["arguments"])
        except ToolExecutionError as exc:
            raise HTTPException(422, f"Tool arguments rejected: {exc}") from exc
        verified_calls.append({**entry, "result": result})

    # We return to the LLM with each actual, validated tool result.
    messages.append({"role": "assistant", "tool_calls": calls})
    for entry in verified_calls:
        messages.append({
            "role": "tool",
            "tool_name": entry["name"],
            "content": json.dumps(entry["result"], ensure_ascii=False),
        })
        used.append({"name": entry["name"], "result": entry["result"]})

    final = await call_model({
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {"temperature": 0, "num_predict": 220},
    })
    if final.get("tool_calls"):
        raise HTTPException(502, "Tool call limit reached")
    answer = final.get("content")
    if not isinstance(answer, str) or not answer.strip():
        raise HTTPException(502, "AI returned no final answer")
    return ToolChatResponse(answer=answer.strip(), model=MODEL, tools_used=used)


@router.get("/tools", include_in_schema=False)
async def tools_page():
    file = Path(__file__).resolve().parents[1] / "frontend" / "tools.html"
    if not file.is_file():
        raise HTTPException(404, "Tool interface missing")
    return FileResponse(file)
