"""Isolated cloud API factory. Not mounted in the original app or publicly deployed."""
from typing import Annotated, Literal
from urllib.parse import urlsplit
from fastapi import FastAPI, Request, Response, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator
from backend.cloud_ai import CloudAIError
from backend.cloud_limits import CloudLimitExceeded

COOKIE = '__Host-knowledgeai_session'
MAX_BODY = 80000

class StrictBody(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

class Credentials(StrictBody):
    email: Annotated[str, StringConstraints(min_length=3, max_length=254)]
    password: Annotated[str, StringConstraints(min_length=12, max_length=128)]

class ConsentedBody(StrictBody):
    consent: Literal[True]

    @field_validator("consent", mode="before")
    @classmethod
    def require_consent(cls, value):
        if value is not True:
            raise ValueError("Explicit consent required")
        return value

class Question(ConsentedBody):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=800)]

class Chat(ConsentedBody):
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]

class Upload(ConsentedBody):
    filename: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    text: Annotated[str, StringConstraints(min_length=1, max_length=12000)]

class Boundary:
    def __init__(self, app, origin):
        self.app, self.origin = app, origin

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = dict(scope['headers'])
        async def secured(message):
            if message['type'] == 'http.response.start':
                message['headers'] = list(message.get('headers', [])) + [
                    (b'cache-control', b'no-store'), (b'x-content-type-options', b'nosniff'),
                    (b'x-frame-options', b'DENY'), (b'referrer-policy', b'no-referrer')]
            await send(message)
        async def reject(status, detail):
            await JSONResponse({'detail':detail},status_code=status)(scope,receive,secured)
        if scope['method'] not in ('GET','HEAD','OPTIONS'):
            if headers.get(b'origin') != self.origin.encode('ascii'):
                return await reject(403,'Origin not allowed')
            if scope['method'] == 'POST' and headers.get(b'content-type',b'').split(b';')[0].strip().lower() != b'application/json':
                return await reject(415,'JSON required')
        # Count actual bytes, including requests without Content-Length.
        data = bytearray()
        while True:
            msg = await receive()
            if msg['type'] == 'http.disconnect':
                return
            if msg['type'] != 'http.request':
                continue
            data.extend(msg.get('body',b''))
            if len(data)>MAX_BODY:
                return await reject(413,'Request too large')
            if not msg.get('more_body',False):
                break
        sent = False
        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {'type':'http.request','body':bytes(data),'more_body':False}
            return await receive()
        await self.app(scope,replay,secured)


def create_cloud_app(store, core, limits, origin):
    p = urlsplit(origin)
    if p.scheme != 'https' or not p.netloc or p.path or p.query or p.fragment or p.username or p.password or not origin.isascii():
        raise ValueError('Expected exact HTTPS origin')
    app = FastAPI(title='KnowledgeAI Cloud API',docs_url=None,redoc_url=None,openapi_url=None)
    app.add_middleware(Boundary,origin=origin)

    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        return JSONResponse({'detail':'Invalid request'},status_code=422)

    @app.exception_handler(CloudLimitExceeded)
    async def limited(request, exc):
        return JSONResponse({'detail':'Daily request budget reached'},status_code=429)

    @app.exception_handler(CloudAIError)
    async def ai_error(request, exc):
        return JSONResponse({'detail':'AI service temporarily unavailable'},status_code=503)

    @app.exception_handler(ValueError)
    async def bad_input(request, exc):
        return JSONResponse({'detail':'Invalid request or quota exceeded'},status_code=400)

    @app.exception_handler(Exception)
    async def internal(request, exc):
        return JSONResponse({'detail':'Service temporarily unavailable'},status_code=503,headers={'Cache-Control':'no-store'})

    def identity(request: Request):
        token = request.cookies.get(COOKIE,'')
        uid = store.session_owner(token)
        if uid is None:
            raise HTTPException(401,'Authentication required')
        return uid

    @app.get('/api/cloud/health')
    def health():
        return {'status':'ok','mode':'cloud-api'}

    @app.post('/api/cloud/register',status_code=201)
    def register(data: Credentials):
        limits.consume('register')
        try:
            store.create_user(data.email,data.password)
        except Exception as exc:
            if getattr(exc,'sqlstate',None) == '23505':
                raise HTTPException(409,'Unable to register') from None
            raise
        return {'status':'registered'}

    @app.post('/api/cloud/login')
    def login(data: Credentials, request: Request, response: Response):
        limits.consume('auth')
        uid = store.authenticate(data.email,data.password)
        if uid is None:
            raise HTTPException(401,'Invalid credentials')
        old = request.cookies.get(COOKIE,'')
        if store.session_owner(old) is not None:
            store.revoke_session(old)
        token = store.issue_session(uid)
        response.set_cookie(COOKIE,token,max_age=7*86400,secure=True,httponly=True,samesite='strict',path='/')
        return {'status':'authenticated'}

    @app.get('/api/cloud/me')
    def me(uid=Depends(identity)):
        return {'authenticated':True}

    @app.post('/api/cloud/logout')
    def logout(request: Request,response: Response,uid=Depends(identity)):
        store.revoke_session(request.cookies[COOKIE])
        response.delete_cookie(COOKIE,path='/',secure=True,httponly=True,samesite='strict')
        return {'status':'logged_out'}

    @app.get('/api/cloud/documents')
    def documents(uid=Depends(identity)):
        return {'documents':store.list_documents(uid)}

    @app.post('/api/cloud/documents',status_code=201)
    def upload(data: Upload,uid=Depends(identity)):
        if len(data.text.encode('utf-8'))>12000 or '\x00' in data.text:
            raise ValueError('Invalid document')
        limits.consume('ai',uid,4)
        chunks = core.index_document(data.filename,data.text.encode('utf-8'))
        try:
            doc_id = store.save_document(uid,chunks)
        except Exception as exc:
            if getattr(exc,'sqlstate',None)=='23505':
                raise HTTPException(409,'Document already exists') from None
            raise
        return {'document_id':doc_id}

    @app.delete('/api/cloud/documents/{doc_id}')
    def delete(doc_id: Annotated[str,StringConstraints(pattern=r'^[a-f0-9]{32}$')],uid=Depends(identity)):
        if not store.delete_document(uid,doc_id):
            raise HTTPException(404,'Document not found')
        return {'status':'deleted'}

    @app.post('/api/cloud/chat')
    def chat(data: Chat,uid=Depends(identity)):
        limits.consume('ai',uid,1)
        return core.chat(data.message)

    @app.post('/api/cloud/structured')
    def structured(data: Question,uid=Depends(identity)):
        limits.consume('ai',uid,1)
        return core.structured(data.question)

    @app.post('/api/cloud/ask')
    def ask(data: Question,uid=Depends(identity)):
        limits.consume('ai',uid,2)
        return core.ask(data.question,store.load_chunks(uid))

    return app
