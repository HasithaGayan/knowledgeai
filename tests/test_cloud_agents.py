import uuid
import pytest
from fastapi.testclient import TestClient
from backend.cloud_agents import create_agent_app
from backend.cloud_ai import CloudAIError
from test_cloud_api import Store,Limits,ORIGIN,HEAD,login
from test_cloud_conversations import Conversations

P='/api/cloud/agents'
BODY={'title':'Study notes','text':'A factual note about databases.','numbers':[2,4,6],'consent':True}
class AI:
    def chat(self,messages,**kwargs): return 'Draft summary.'
class Core:
    ai=AI()
class Runs:
    def __init__(self): self.rows={}
    def create(self,u,title,draft,trace):
        rid=str(uuid.uuid4()); self.rows[u,rid]=dict(id=rid,title=title,draft=draft,trace=trace,status='pending'); return rid
    def list(self,u): return [r for (owner,_),r in self.rows.items() if owner==u]
    def get(self,u,rid): return self.rows.get((u,str(rid)))
    def decide(self,u,rid,approve):
        row=self.get(u,rid)
        if row and row['status']=='pending':
            row['status']='approved' if approve else 'rejected'; return row['status']
    def delete(self,u,rid): return self.rows.pop((u,str(rid)),None) is not None
@pytest.fixture
def setup():
    s,c,l,r=Store(),Core(),Limits(),Runs()
    app=create_agent_app(s,c,l,ORIGIN,r,Conversations())
    a,b=TestClient(app,base_url=ORIGIN),TestClient(app,base_url=ORIGIN)
    login(a); login(b,{'email':'b@example.invalid','password':'another-long-password'})
    return a,b,c,l,r

def create(a):
    res=a.post(P,json=BODY,headers=HEAD); assert res.status_code==201
    return P+'/'+res.json()['id']

def test_approval(setup):
    a,b,c,l,r=setup; p=create(a)
    assert a.get(p+'/report').status_code==409
    assert 'Average of 3 supplied numbers: 4.0' in a.get(p).json()['draft']
    assert a.post(p+'/decision',json={'approve':True},headers=HEAD).json()['status']=='approved'
    report=a.get(p+'/report'); assert report.status_code==200 and 'attachment' in report.headers['content-disposition']
    assert a.post(p+'/decision',json={'approve':False},headers=HEAD).status_code==409

def test_isolation(setup):
    a,b,c,l,r=setup; p=create(a)
    assert b.get(P).json()=={'workflows':[]}
    assert b.get(p).status_code==404 and b.get(p+'/report').status_code==404
    assert b.post(p+'/decision',json={'approve':True},headers=HEAD).status_code==404
    assert b.delete(p,headers=HEAD).status_code==404
    assert a.delete(p,headers=HEAD).status_code==200

def test_reject(setup):
    a,b,c,l,r=setup; p=create(a)
    assert a.post(p+'/decision',json={'approve':False},headers=HEAD).json()['status']=='rejected'
    assert a.get(p+'/report').status_code==409

def test_expiry(setup):
    a,b,c,l,r=setup; p=create(a); next(iter(r.rows.values()))['status']='expired'
    assert a.post(p+'/decision',json={'approve':True},headers=HEAD).status_code==409
    assert a.get(p+'/report').status_code==409

@pytest.mark.parametrize('patch',[{'consent':False},{'numbers':[True]},{'numbers':['2']},{'numbers':[1000001]},{'owner':'victim'},{'text':'  '}])
def test_input(setup,patch):
    a,b,c,l,r=setup; assert a.post(P,json=BODY|patch,headers=HEAD).status_code==422

def test_origin_budget(setup):
    a,b,c,l,r=setup
    assert a.post(P,json=BODY,headers={'Origin':'https://wrong.invalid'}).status_code==403
    l.block=True; assert a.post(P,json=BODY,headers=HEAD).status_code==429
    assert not r.rows

def test_logout(setup):
    a,b,c,l,r=setup; p=create(a)
    a.post('/api/cloud/logout',json={},headers=HEAD)
    assert a.get(p).status_code==401

def test_limit(setup):
    a,b,c,l,r=setup
    for _ in range(8): create(a)
    assert a.post(P,json=BODY,headers=HEAD).status_code==409
