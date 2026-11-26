import copy
import uuid
import pytest
from fastapi.testclient import TestClient
from backend.cloud_conversations import create_conversation_app
from test_cloud_api import Store, Limits, ORIGIN, HEAD, login

class Conversations:
    def __init__(self): self.rows={}; self.conflict=False
    def create(self,owner,title):
        cid=str(uuid.uuid4()); self.rows[owner,cid]={'id':cid,'title':title,'revision':0,'messages':[]}; return cid
    def list(self,owner): return [r for (u,_),r in self.rows.items() if u==owner]
    def get(self,owner,cid): return copy.deepcopy(self.rows.get((owner,str(cid))))
    def delete(self,owner,cid): return self.rows.pop((owner,str(cid)),None) is not None
    def append(self,owner,cid,rev,history,message,answer):
        row=self.rows[owner,str(cid)]
        if self.conflict or row['revision']!=rev: return None
        row['messages']=history+[{'role':'user','content':message},{'role':'assistant','content':answer}]; row['revision']+=1
        return row['revision']

class Core:
    def __init__(self): self.history=[]
    def chat(self,message,history=()): self.history=history; return {'answer':'reply','model':'fake'}

P='/api/cloud/conversations'
@pytest.fixture
def setup():
    s,c,l,v=Store(),Core(),Limits(),Conversations()
    app=create_conversation_app(s,c,l,ORIGIN,v)
    a,b=TestClient(app,base_url=ORIGIN),TestClient(app,base_url=ORIGIN)
    login(a); login(b,{'email':'b@example.invalid','password':'another-long-password'})
    cid=a.post(P,json={'title':'Private'},headers=HEAD).json()['id']
    return a,b,c,l,v,cid

def test_isolation(setup):
    a,b,c,l,v,cid=setup
    assert b.get(P).json()=={'conversations':[]}
    assert b.get(P+'/'+cid).status_code==404
    assert b.delete(P+'/'+cid,headers=HEAD).status_code==404
    assert b.post(P+'/'+cid+'/messages',json={'message':'hi','consent':True},headers=HEAD).status_code==404
    assert a.get(P+'/'+cid).status_code==200

def test_history(setup):
    a,b,c,l,v,cid=setup; path=P+'/'+cid+'/messages'
    assert a.post(path,json={'message':'one','consent':True},headers=HEAD).status_code==200
    assert a.post(path,json={'message':'two','consent':True},headers=HEAD).json()['revision']==2
    assert c.history==[{'role':'user','content':'one'},{'role':'assistant','content':'reply'}]
    assert len(a.get(P+'/'+cid).json()['messages'])==4
    assert a.delete(P+'/'+cid,headers=HEAD).status_code==200
    assert a.get(P+'/'+cid).status_code==404

@pytest.mark.parametrize('body',[{'message':'hi'},{'message':'hi','consent':False},{'message':'hi','consent':True,'history':[]},{'message':'hi','consent':True,'owner':'b'}])
def test_consent(setup,body):
    a,b,c,l,v,cid=setup
    assert a.post(P+'/'+cid+'/messages',json=body,headers=HEAD).status_code==422

def test_conflict(setup):
    a,b,c,l,v,cid=setup; v.conflict=True
    assert a.post(P+'/'+cid+'/messages',json={'message':'hi','consent':True},headers=HEAD).status_code==409
    assert a.get(P+'/'+cid).json()['messages']==[]

def test_budget(setup):
    a,b,c,l,v,cid=setup; l.block=True
    assert a.post(P+'/'+cid+'/messages',json={'message':'hi','consent':True},headers=HEAD).status_code==429
    assert a.get(P+'/'+cid).json()['messages']==[]

def test_full(setup):
    a,b,c,l,v,cid=setup
    row=next(iter(v.rows.values())); row['messages']=[{'role':'user','content':'hi'},{'role':'assistant','content':'reply'}]*10
    assert a.post(P+'/'+cid+'/messages',json={'message':'hi','consent':True},headers=HEAD).status_code==409

def test_origin_logout(setup):
    a,b,c,l,v,cid=setup
    assert a.delete(P+'/'+cid,headers={'Origin':'https://wrong.invalid'}).status_code==403
    assert a.post('/api/cloud/logout',json={},headers=HEAD).status_code==200
    assert a.get(P+'/'+cid).status_code==401

def test_bad_title(setup):
    a,b,c,l,v,cid=setup
    assert a.post(P,json={'title':'   '},headers=HEAD).status_code==422
