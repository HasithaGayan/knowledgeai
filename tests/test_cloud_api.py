import pytest
from fastapi.testclient import TestClient
from backend.cloud_api import create_cloud_app, COOKIE
from backend.cloud_limits import CloudLimitExceeded
from backend.cloud_ai import CloudAIError

ORIGIN='https://knowledgeai.example.invalid'
HEAD={'Origin':ORIGIN}
DOC='a'*32
CREDS={'email':'a@example.invalid','password':'a-long-password'}

class Store:
    def __init__(self): self.users={}; self.sessions={}; self.docs={}
    def create_user(self,e,p): self.users[e]=p; return e
    def authenticate(self,e,p): return e if self.users.get(e)==p else None
    def session_owner(self,t): return self.sessions.get(t)
    def issue_session(self,u): self.sessions['token-'+u]=''+u; return 'token-'+u
    def revoke_session(self,t): self.sessions.pop(t,None)
    def list_documents(self,u): return self.docs.get(u,[])
    def save_document(self,u,chunks): self.docs.setdefault(u,[]).extend(chunks); return DOC
    def load_chunks(self,u): return self.list_documents(u)
    def delete_document(self,u,d): return bool(self.docs.pop(u,None))
class Limits:
    def __init__(self): self.calls=[]; self.block=False
    def consume(self,*a):
        self.calls.append(a)
        if self.block: raise CloudLimitExceeded()
class Core:
    def index_document(self,name,content): return [{'document_id':DOC,'source':name,'text':content.decode()}]
    def ask(self,q,chunks): return {'answer':chunks[0]['text'] if chunks else 'no evidence'}
    def chat(self,m): return {'answer':m}
    def structured(self,q): return {'answer':q}
@pytest.fixture
def setup():
    s,l,c=Store(),Limits(),Core()
    app=create_cloud_app(s,c,l,ORIGIN)
    return s,l,c,TestClient(app,base_url=ORIGIN),TestClient(app,base_url=ORIGIN)
def login(client,creds=CREDS):
    assert client.post('/api/cloud/register',json=creds,headers=HEAD).status_code==201
    return client.post('/api/cloud/login',json=creds,headers=HEAD)
def test_session(setup):
    s,l,c,a,b=setup
    r=login(a); assert r.status_code==200
    cookie=r.headers['set-cookie'].lower()
    assert all(x in cookie for x in ('httponly','secure','samesite=strict','path=/'))
    assert 'token-' not in r.text and a.get('/api/cloud/me').status_code==200
    assert b.get('/api/cloud/me').status_code==401
    assert a.post('/api/cloud/logout',json={},headers=HEAD).status_code==200
    assert a.get('/api/cloud/me').status_code==401
@pytest.mark.parametrize('headers',[{}, {'Origin':'https://attacker.invalid'}])
def test_origin(setup,headers):
    s,l,c,a,b=setup
    assert a.post('/api/cloud/register',json=CREDS,headers=headers).status_code==403
    assert not l.calls
@pytest.mark.parametrize('path,body',[('chat',{'message':'hi','consent':True}),('structured',{'question':'hi','consent':True}),('ask',{'question':'hi','consent':True}),('documents',{'filename':'a.txt','text':'hello','consent':True})])
def test_unauthenticated(setup,path,body):
    s,l,c,a,b=setup
    assert a.post('/api/cloud/'+path,json=body,headers=HEAD).status_code==401
    assert not l.calls
@pytest.mark.parametrize('body',[{'message':'hello'}, {'message':'hello','consent':False},{'message':'hello','consent':1},{'message':'hi','consent':True,'owner':'victim'},{'message':' ','consent':True}])
def test_consent_and_owner(setup,body):
    s,l,c,a,b=setup; login(a)
    assert a.post('/api/cloud/chat',json=body,headers=HEAD).status_code==422
    assert len(l.calls)==2

def test_isolation(setup):
    s,l,c,a,b=setup; login(a); login(b,{'email':'b@example.invalid','password':'another-long-password'})
    assert a.post('/api/cloud/documents',json={'filename':'a.txt','text':'A only','consent':True},headers=HEAD).status_code==201
    assert b.get('/api/cloud/documents').json()=={'documents':[]}
    assert b.post('/api/cloud/ask',json={'question':'what','consent':True},headers=HEAD).json()['answer']=='no evidence'
    assert b.delete('/api/cloud/documents/'+DOC,headers=HEAD).status_code==404
    assert a.post('/api/cloud/ask',json={'question':'what','consent':True},headers=HEAD).json()['answer']=='A only'
    assert a.delete('/api/cloud/documents/'+DOC,headers=HEAD).status_code==200

def test_limit(setup):
    s,l,c,a,b=setup; login(a); l.block=True
    assert a.post('/api/cloud/chat',json={'message':'hi','consent':True},headers=HEAD).status_code==429

def test_body_limit(setup):
    s,l,c,a,b=setup
    assert a.post('/api/cloud/register',content=b'x'*80001,headers=HEAD|{'Content-Type':'application/json'}).status_code==413

def test_content_type(setup):
    s,l,c,a,b=setup
    assert a.post('/api/cloud/register',data=CREDS,headers=HEAD).status_code==415

def test_no_sensitive_validation_output(setup):
    s,l,c,a,b=setup
    r=a.post('/api/cloud/login',json={'email':'a','password':'secret'},headers=HEAD)
    assert r.status_code==422 and 'secret' not in r.text and r.headers['cache-control']=='no-store'

def test_provider_error(setup):
    s,l,c,a,b=setup; login(a)
    def fail(message): raise CloudAIError('private provider error')
    c.chat=fail
    r=a.post('/api/cloud/chat',json={'message':'hi','consent':True},headers=HEAD)
    assert r.status_code==503 and 'private provider error' not in r.text
