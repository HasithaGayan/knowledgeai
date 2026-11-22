"""Day 74 tests: workspace access, SQLite persistence, streaming, failures."""
import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import conversation_stream as mod

ALICE = {"X-KnowledgeAI-Workspace": "a" * 43}
BOB = {"X-KnowledgeAI-Workspace": "b" * 43}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("KNOWLEDGEAI_CHAT_DB", str(tmp_path / "local.sqlite3"))
    app = FastAPI()
    app.include_router(mod.router)
    return TestClient(app)


def new(client, headers=ALICE):
    res = client.post("/api/conversations", headers=headers)
    assert res.status_code == 201
    return res.json()["id"]


def test_missing_workspace_token(client):
    assert client.get("/api/conversations").status_code == 401
    assert client.post("/api/conversations").status_code == 401


def test_bad_workspace_token(client):
    assert client.post("/api/conversations", headers={"X-KnowledgeAI-Workspace": "abc"}).status_code == 401
    assert client.post("/api/conversations", headers={"X-KnowledgeAI-Workspace": "x" * 42 + "!"}).status_code == 401


def test_create_and_list(client):
    ident = new(client)
    listing = client.get("/api/conversations", headers=ALICE).json()["conversations"]
    assert len(listing) == 1 and listing[0]["id"] == ident


def test_isolation_between_workspaces(client):
    ident = new(client)
    assert client.get(f"/api/conversations/{ident}", headers=BOB).status_code == 404
    assert client.delete(f"/api/conversations/{ident}", headers=BOB).status_code == 404
    assert client.post(f"/api/conversations/{ident}/stream", headers=BOB, json={"message": "Hello"}).status_code == 404
    assert client.get("/api/conversations", headers=BOB).json()["conversations"] == []


def test_read_empty_conversation(client):
    ident = new(client)
    details = client.get(f"/api/conversations/{ident}", headers=ALICE).json()
    assert details["messages"] == [] and details["conversation"]["title"] == "New conversation"


def test_delete_conversation(client):
    ident = new(client)
    assert client.delete(f"/api/conversations/{ident}", headers=ALICE).status_code == 204
    assert client.get(f"/api/conversations/{ident}", headers=ALICE).status_code == 404


def test_delete_unknown_id(client):
    assert client.delete("/api/conversations/missing", headers=ALICE).status_code == 404


def test_blank_stream_input(client):
    ident = new(client)
    assert client.post(f"/api/conversations/{ident}/stream", headers=ALICE, json={"message": "  "}).status_code == 422


def test_oversize_stream_input(client):
    ident = new(client)
    assert client.post(f"/api/conversations/{ident}/stream", headers=ALICE, json={"message": "q" * 2001}).status_code == 422


def test_stream_rejects_extra_fields(client):
    ident = new(client)
    assert client.post(f"/api/conversations/{ident}/stream", headers=ALICE, json={"message": "ok", "admin": True}).status_code == 422


def test_persist_pair_atomic_and_reopened(client):
    ident = new(client)
    mod._persist_pair(ident, mod._owner(ALICE["X-KnowledgeAI-Workspace"]), "Hello", "Hi")
    data = client.get(f"/api/conversations/{ident}", headers=ALICE).json()
    assert [(m["role"],m["content"]) for m in data["messages"]] == [("user", "Hello"), ("assistant", "Hi")]
    assert data["conversation"]["title"] == "Hello"


def test_database_has_only_token_digest(client):
    new(client)
    raw = mod.database_path().read_bytes()
    assert ("a" * 43).encode() not in raw
    assert mod._owner(ALICE["X-KnowledgeAI-Workspace"]).encode() in raw


def test_persist_does_not_allow_wrong_workspace(client):
    ident = new(client)
    with pytest.raises(Exception):
        mod._persist_pair(ident, mod._owner(BOB["X-KnowledgeAI-Workspace"]), "bad", "bad")
    assert client.get(f"/api/conversations/{ident}", headers=ALICE).json()["messages"] == []


def test_message_limit(client):
    ident = new(client)
    owner=mod._owner(ALICE["X-KnowledgeAI-Workspace"])
    for index in range(mod.MAX_MESSAGES // 2):
        mod._persist_pair(ident, owner, str(index), "reply")
    res = client.post(f"/api/conversations/{ident}/stream", headers=ALICE, json={"message": "again"})
    assert res.status_code == 409


def test_local_page(client):
    res = client.get('/conversations')
    assert res.status_code == 200 and 'Conversation Studio' in res.text


class StreamProvider:
    def __init__(self, frames):
        self.frames = frames
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    def raise_for_status(self): pass
    async def aiter_lines(self):
        for frame in self.frames:
            yield json.dumps(frame)


class FakeAsyncClient:
    def __init__(self, frames, **kwargs): self.frames=frames
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    def stream(self, method, url, json):
        assert method == 'POST' and json['stream'] is True
        assert json['model'] == mod.MODEL
        self.payload=json
        return StreamProvider(self.frames)


def provider(monkeypatch, frames):
    monkeypatch.setattr(mod.httpx, 'AsyncClient', lambda **kw: FakeAsyncClient(frames, **kw))


def events(response):
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def test_streaming_model_chunks_and_save(client, monkeypatch):
    ident=new(client)
    provider(monkeypatch,[{"message":{"content":"Hello "},"done":False}, {"message":{"content":"there"},"done":True}])
    response=client.post(f'/api/conversations/{ident}/stream',headers=ALICE,json={'message':'Say hi'})
    assert response.status_code==200
    result=events(response)
    assert [e['type'] for e in result]==['start','delta','delta','done']
    assert ''.join(e['text'] for e in result if e['type']=='delta')=='Hello there'
    assert result[-1]['saved'] is True
    stored=client.get(f'/api/conversations/{ident}',headers=ALICE).json()['messages']
    assert [m['content'] for m in stored] == ['Say hi','Hello there']


def test_stream_rejects_malformed_json(client, monkeypatch):
    ident=new(client)
    class BadProvider(StreamProvider):
        async def aiter_lines(self): yield '{not json'
    class BadClient(FakeAsyncClient):
        def stream(self, *args, **kwargs): return BadProvider([])
    monkeypatch.setattr(mod.httpx, 'AsyncClient', lambda **kw: BadClient([], **kw))
    res=client.post(f'/api/conversations/{ident}/stream',headers=ALICE,json={'message':'hi'})
    assert events(res)[-1]['type']=='error'
    assert client.get(f'/api/conversations/{ident}',headers=ALICE).json()['messages']==[]


def test_stream_provider_error_not_saved(client, monkeypatch):
    ident=new(client)
    provider(monkeypatch,[{'error':'do not leak provider details'}])
    res=client.post(f'/api/conversations/{ident}/stream',headers=ALICE,json={'message':'hi'})
    assert events(res)[-1]['type']=='error'
    assert 'do not leak' not in res.text
    assert client.get(f'/api/conversations/{ident}',headers=ALICE).json()['messages']==[]


def test_stream_empty_response_not_saved(client, monkeypatch):
    ident=new(client)
    provider(monkeypatch,[{'message':{'content':''},'done':True}])
    res=client.post(f'/api/conversations/{ident}/stream',headers=ALICE,json={'message':'hi'})
    assert events(res)[-1]['type']=='error'
    assert client.get(f'/api/conversations/{ident}',headers=ALICE).json()['messages']==[]


def test_retrieval_context_limited_to_ten_messages(client, monkeypatch):
    ident=new(client)
    owner=mod._owner(ALICE['X-KnowledgeAI-Workspace'])
    for i in range(7): mod._persist_pair(ident,owner,str(i),'answer')
    calls=[]
    class WatchingClient(FakeAsyncClient):
        def stream(self, method,url,json):
            calls.append(json)
            return StreamProvider([{'message':{'content':'Okay'},'done':True}])
    monkeypatch.setattr(mod.httpx,'AsyncClient',lambda **kw:WatchingClient([],**kw))
    res=client.post(f'/api/conversations/{ident}/stream',headers=ALICE,json={'message':'new'})
    assert res.status_code==200
    assert len(calls[0]['messages'])==12   # system + last 10 + current user


def test_max_conversations_enforced(client, monkeypatch):
    monkeypatch.setattr(mod,'MAX_CONVERSATIONS',2)
    new(client); new(client)
    assert client.post('/api/conversations',headers=ALICE).status_code==429
