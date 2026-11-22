"""KnowledgeAI Day 74: local workspace-scoped, durable streaming conversations.

This is a single-user development prototype, NOT production authentication.
Store only workspace-token digests, never plaintext access tokens. Do not expose
this application to the public internet without real identity/authorization.
"""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter()
MODEL = "qwen3:0.6b"
OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"
SYSTEM_PROMPT = (
    "You are KnowledgeAI, a careful educational assistant. "
    "Give concise, accurate answers; express uncertainty. "
    "No user documents are connected to this conversation; do not claim to search them."
)
MAX_MESSAGES = 80
MAX_CONVERSATIONS = 40
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43,128}$")


def database_path() -> Path:
    custom = os.environ.get("KNOWLEDGEAI_CHAT_DB")
    return Path(custom) if custom else Path(__file__).resolve().parents[1] / "data" / "day74_conversations.sqlite3"


def _db() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=5)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            owner_hash TEXT NOT NULL,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_owner ON conversations(owner_hash,updated_at)")
    con.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK(role IN ('user','assistant')),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    return con


@contextmanager
def _connection():
    con = _db()
    try:
        with con:
            yield con
    finally:
        con.close()


def _owner(token: str | None) -> str:
    if token is None or TOKEN_PATTERN.fullmatch(token) is None:
        raise HTTPException(401, "A local workspace token is required")
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _find(con: sqlite3.Connection, conversation_id: str, owner: str) -> sqlite3.Row:
    row = con.execute(
        "SELECT * FROM conversations WHERE id = ? AND owner_hash = ?",
        (conversation_id, owner),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Conversation not found")
    return row


class SendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=2000)


@router.get("/conversations", include_in_schema=False)
async def conversation_page():
    file = Path(__file__).resolve().parents[1] / "frontend" / "conversations.html"
    if not file.is_file():
        raise HTTPException(404, "Conversation Studio page unavailable")
    return FileResponse(file)


@router.post("/api/conversations", status_code=201)
async def create_conversation(x_knowledgeai_workspace: str | None = Header(default=None)):
    owner = _owner(x_knowledgeai_workspace)
    ident = secrets.token_urlsafe(18)
    now = _now()
    with _connection() as con:
        count = con.execute("SELECT COUNT(*) FROM conversations WHERE owner_hash=?", (owner,)).fetchone()[0]
        if count >= MAX_CONVERSATIONS:
            raise HTTPException(429, "Local workspace conversation limit reached")
        con.execute(
            "INSERT INTO conversations(id,owner_hash,title,created_at,updated_at) VALUES(?,?,?,?,?)",
            (ident, owner, "New conversation", now, now),
        )
    return {"id": ident, "title": "New conversation", "created_at": now}


@router.get("/api/conversations")
async def list_conversations(x_knowledgeai_workspace: str | None = Header(default=None)):
    owner = _owner(x_knowledgeai_workspace)
    with _connection() as con:
        rows = con.execute(
            "SELECT id,title,created_at,updated_at FROM conversations WHERE owner_hash=? "
            "ORDER BY updated_at DESC LIMIT ?", (owner, MAX_CONVERSATIONS)
        ).fetchall()
        return {"conversations": [dict(row) for row in rows]}


@router.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, x_knowledgeai_workspace: str | None = Header(default=None)):
    owner = _owner(x_knowledgeai_workspace)
    with _connection() as con:
        row = _find(con, conversation_id, owner)
        msgs = con.execute(
            "SELECT role,content,created_at FROM messages WHERE conversation_id=? ORDER BY id", (conversation_id,)
        ).fetchall()
        return {"conversation": {k: row[k] for k in ("id", "title", "created_at", "updated_at")},
                "messages": [dict(msg) for msg in msgs]}


@router.delete("/api/conversations/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str, x_knowledgeai_workspace: str | None = Header(default=None)):
    owner = _owner(x_knowledgeai_workspace)
    with _connection() as con:
        _find(con, conversation_id, owner)
        con.execute("DELETE FROM conversations WHERE id=? AND owner_hash=?", (conversation_id, owner))


def _frame(kind: str, **data) -> bytes:
    return (json.dumps({"type": kind, **data}, ensure_ascii=False) + "\n").encode("utf-8")


def _persist_pair(conversation_id: str, owner: str, user_message: str, answer: str) -> None:
    """Store complete exchanges atomically. Aborted streams never call this."""
    when = _now()
    with _connection() as con:
        row = _find(con, conversation_id, owner)
        count = con.execute("SELECT COUNT(*) FROM messages WHERE conversation_id=?", (conversation_id,)).fetchone()[0]
        if count + 2 > MAX_MESSAGES:
            raise HTTPException(409, "Conversation reached its message limit; start a new one")
        for role, content in (("user", user_message), ("assistant", answer)):
            con.execute(
                "INSERT INTO messages(conversation_id,role,content,created_at) VALUES(?,?,?,?)",
                (conversation_id, role, content, when),
            )
        title = row["title"]
        if title == "New conversation" and count == 0:
            title = user_message[:64]
        con.execute("UPDATE conversations SET title=?,updated_at=? WHERE id=?", (title, when, conversation_id))


@router.post("/api/conversations/{conversation_id}/stream")
async def stream_conversation(
    conversation_id: str,
    payload: SendRequest,
    request: Request,
    x_knowledgeai_workspace: str | None = Header(default=None),
):
    owner = _owner(x_knowledgeai_workspace)
    question = payload.message.strip()
    if not question:
        raise HTTPException(422, "Message cannot be blank")
    with _connection() as con:
        _find(con, conversation_id, owner)
        count = con.execute("SELECT COUNT(*) FROM messages WHERE conversation_id=?", (conversation_id,)).fetchone()[0]
        if count + 2 > MAX_MESSAGES:
            raise HTTPException(409, "Conversation reached its message limit")
        rows = con.execute(
            "SELECT role,content FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT 10",
            (conversation_id,),
        ).fetchall()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(dict(row) for row in reversed(rows))
    messages.append({"role": "user", "content": question})

    async def stream_events():
        chunks: list[str] = []
        total_length = 0
        yield _frame("start", model=MODEL)
        try:
            timeout = httpx.Timeout(connect=10, read=90, write=10, pool=10)
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", OLLAMA_CHAT_URL, json={
                    "model": MODEL, "messages": messages, "stream": True, "think": False,
                    "options": {"temperature": 0.2, "num_predict": 350},
                }) as upstream:
                    upstream.raise_for_status()
                    async for line in upstream.aiter_lines():
                        if await request.is_disconnected():
                            return
                        if not line.strip():
                            continue
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            yield _frame("error", detail="Model returned malformed streaming data")
                            return
                        if not isinstance(event, dict) or event.get("error"):
                            yield _frame("error", detail="Local model reported a streaming failure")
                            return
                        content = event.get("message", {}).get("content", "")
                        if not isinstance(content, str):
                            yield _frame("error", detail="Model returned invalid text")
                            return
                        if content:
                            total_length += len(content)
                            if total_length > 12000:
                                yield _frame("error", detail="Model output exceeded the safe limit")
                                return
                            chunks.append(content)
                            yield _frame("delta", text=content)
                        if event.get("done"):
                            break
        except httpx.TimeoutException:
            yield _frame("error", detail="Local AI streaming timed out")
            return
        except httpx.HTTPError:
            yield _frame("error", detail="Cannot reach the local AI model")
            return
        if await request.is_disconnected():
            return
        answer = "".join(chunks).strip()
        if not answer:
            yield _frame("error", detail="The model returned no answer")
            return
        try:
            _persist_pair(conversation_id, owner, question, answer)
        except HTTPException as exc:
            yield _frame("error", detail=exc.detail)
            return
        yield _frame("done", saved=True)

    return StreamingResponse(stream_events(), media_type="application/x-ndjson", headers={
        "Cache-Control": "no-store", "X-Accel-Buffering": "no", "X-Content-Type-Options": "nosniff",
    })
