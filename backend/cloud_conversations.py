"""Private saved chat conversations; owner IDs come from the authenticated API."""
import uuid
from typing import Annotated
from fastapi import Depends, HTTPException, Request
from pydantic import StringConstraints
from backend.cloud_api import create_cloud_app, COOKIE, StrictBody, Chat
from backend.cloud_ai import CloudAIError

MAX_CONVERSATIONS = 8
MAX_MESSAGES = 20

class ConversationTitle(StrictBody):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]

class ConversationStorage:
    def __init__(self, store):
        self.store = store

    def create(self, owner, title):
        cid = uuid.uuid4()
        with self.store.connect() as conn:
            if conn.execute('SELECT id FROM knowledgeai_v1.users WHERE id=%s FOR UPDATE',(owner,)).fetchone() is None:
                raise ValueError('Unknown owner')
            if conn.execute('SELECT count(*) FROM knowledgeai_v1.conversations WHERE user_id=%s',(owner,)).fetchone()[0]>=MAX_CONVERSATIONS:
                raise ValueError('Conversation limit reached')
            conn.execute('INSERT INTO knowledgeai_v1.conversations(user_id,id,title) VALUES (%s,%s,%s)',(owner,cid,title))
        return str(cid)

    def list(self, owner):
        with self.store.connect() as conn:
            rows=conn.execute('SELECT id,title,revision FROM knowledgeai_v1.conversations WHERE user_id=%s ORDER BY updated_at DESC,id LIMIT 8',(owner,)).fetchall()
        return [dict(id=str(r[0]),title=r[1],revision=r[2]) for r in rows]

    def get(self, owner, cid):
        with self.store.connect() as conn:
            row=conn.execute('SELECT title,revision,messages FROM knowledgeai_v1.conversations WHERE user_id=%s AND id=%s',(owner,cid)).fetchone()
        return dict(id=str(cid),title=row[0],revision=row[1],messages=row[2]) if row else None

    def append(self, owner, cid, revision, history, message, answer):
        from psycopg.types.json import Jsonb
        if len(history)>=MAX_MESSAGES or not isinstance(answer,str) or not answer.strip() or len(answer)>2000:
            raise ValueError('Invalid conversation turn')
        messages=history+[{'role':'user','content':message},{'role':'assistant','content':answer}]
        with self.store.connect() as conn:
            row=conn.execute('''UPDATE knowledgeai_v1.conversations SET messages=%s,revision=revision+1,updated_at=now()
                WHERE user_id=%s AND id=%s AND revision=%s RETURNING revision''',(Jsonb(messages),owner,cid,revision)).fetchone()
        return row[0] if row else None

    def delete(self, owner, cid):
        with self.store.connect() as conn:
            return conn.execute('DELETE FROM knowledgeai_v1.conversations WHERE user_id=%s AND id=%s',(owner,cid)).rowcount==1


def create_conversation_app(store, core, limits, origin, conversations=None):
    app=create_cloud_app(store,core,limits,origin)
    conv=conversations if conversations is not None else ConversationStorage(store)
    def identity(request: Request):
        owner=store.session_owner(request.cookies.get(COOKIE,''))
        if owner is None:
            raise HTTPException(401,'Authentication required')
        return owner

    @app.get('/api/cloud/conversations')
    def list_conversations(owner=Depends(identity)):
        return {'conversations':conv.list(owner)}

    @app.post('/api/cloud/conversations',status_code=201)
    def create(data: ConversationTitle,owner=Depends(identity)):
        return {'id':conv.create(owner,data.title)}

    @app.get('/api/cloud/conversations/{cid}')
    def get(cid: uuid.UUID,owner=Depends(identity)):
        row=conv.get(owner,cid)
        if row is None: raise HTTPException(404,'Conversation not found')
        return row

    @app.delete('/api/cloud/conversations/{cid}')
    def delete(cid: uuid.UUID,owner=Depends(identity)):
        if not conv.delete(owner,cid): raise HTTPException(404,'Conversation not found')
        return {'status':'deleted'}

    @app.post('/api/cloud/conversations/{cid}/messages')
    def send(cid: uuid.UUID,data: Chat,owner=Depends(identity)):
        row=conv.get(owner,cid)
        if row is None: raise HTTPException(404,'Conversation not found')
        history=row['messages']
        if len(history)>=MAX_MESSAGES: raise HTTPException(409,'Conversation full; start a new one')
        # History is server-derived; user consent covers sending recent turns to AI.
        limits.consume('ai',owner,2)
        result=core.chat(data.message,history[-10:])
        answer=result.get('answer')
        if not isinstance(answer,str) or not answer.strip() or len(answer)>2000:
            raise CloudAIError('Invalid conversation answer')
        rev=conv.append(owner,cid,row['revision'],history,data.message,answer)
        if rev is None: raise HTTPException(409,'Conversation changed; refresh before retrying')
        return {'answer':answer,'model':result.get('model'),'revision':rev}

    return app
