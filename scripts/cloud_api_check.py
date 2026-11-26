"""Real Neon, actual HTTP application boundary, simulated model. No public server.
Use only the dedicated KnowledgeAI project. No credentials printed or saved.
Global request counters intentionally remain; do not repeatedly rerun today.
"""
import json
import secrets
import sys
import uuid
from fastapi.testclient import TestClient
from backend.cloud_storage import CloudStorage
from backend.cloud_limits import CloudLimits, CloudLimitExceeded
from backend.cloud_core import CloudCore
from backend.cloud_api import create_cloud_app, COOKIE

ORIGIN='https://knowledgeai.example.invalid'
H={'Origin':ORIGIN}
PREFIX='/api/cloud/'

class SimulatedAI:
    def embed(self,texts):
        return [[1.0]+[0.0]*383 for _ in texts]
    def chat(self,messages,**kwargs):
        return json.dumps({'supported':True,'answer':'LKR 2500','evidence_quote':'The workshop fee is LKR 2500.'})

def check(condition,label):
    if not condition:
        raise RuntimeError(label)
    print(label+': PASS',flush=True)

def main():
    store=CloudStorage(sys.stdin.read())
    store.migrate()
    limits=CloudLimits(store)
    limits.migrate()
    app=create_cloud_app(store,CloudCore(SimulatedAI()),limits,ORIGIN)
    a=TestClient(app,base_url=ORIGIN,raise_server_exceptions=False)
    b=TestClient(app,base_url=ORIGIN,raise_server_exceptions=False)
    tag=uuid.uuid4().hex
    emails=[f'api-{tag}-{x}@example.invalid' for x in ('a','b')]
    ids=[]
    try:
        check(a.get(PREFIX+'documents').status_code==401,'Unauthenticated HTTP access denied')
        for client,email in zip((a,b),emails):
            creds={'email':email,'password':secrets.token_urlsafe(24)}
            check(client.post(PREFIX+'register',json=creds,headers=H).status_code==201,'Registration')
            r=client.post(PREFIX+'login',json=creds,headers=H)
            check(r.status_code==200,'Login')
            cookie=r.headers.get('set-cookie','').lower()
            check(all(x in cookie for x in ('httponly','secure','samesite=strict','path=/')),'Secure cookie attributes')
            ids.append(store.session_owner(client.cookies[COOKIE]))
        check(ids[0] and ids[1] and ids[0]!=ids[1],'Separate authenticated identities')
        body={'filename':'fictional.txt','text':'The workshop fee is LKR 2500.','consent':True}
        check(a.post(PREFIX+'documents',json=body,headers={'Origin':'https://other.invalid'}).status_code==403,'Cross-origin write denied')
        check(a.post(PREFIX+'documents',json=body|{'consent':False},headers=H).status_code==422,'Explicit consent required')
        r=a.post(PREFIX+'documents',json=body,headers=H)
        check(r.status_code==201,'Persistent document creation')
        doc=r.json()['document_id']
        check(b.get(PREFIX+'documents').json()=={'documents':[]},'Second account cannot list private documents')
        check(b.delete(PREFIX+'documents/'+doc,headers=H).status_code==404,'Second account cannot delete private document')
        question={'question':'What is the workshop fee?','consent':True}
        check(b.post(PREFIX+'ask',json=question,headers=H).json().get('status')=='no_evidence','Second account cannot retrieve private evidence')
        check(a.post(PREFIX+'ask',json=question,headers=H).json().get('status')=='answered','Owner can retrieve evidence')
        check(a.delete(PREFIX+'documents/'+doc,headers=H).status_code==200,'Owner can delete document')
        # Owner has consumed six units; add six and verify the next unit fails.
        limits.consume('ai',ids[0],4); limits.consume('ai',ids[0],2)
        check(a.post(PREFIX+'chat',json={'message':'hello','consent':True},headers=H).status_code==429,'Persistent per-user AI budget enforced')
        check(a.post(PREFIX+'logout',json={},headers=H).status_code==200 and a.get(PREFIX+'me').status_code==401,'Logout revokes session')
    finally:
        with store.connect() as conn:
            rows=conn.execute('SELECT id FROM knowledgeai_v1.users WHERE email IN (%s,%s)',tuple(emails)).fetchall()
            for row in rows:
                conn.execute('DELETE FROM knowledgeai_v1.request_budgets WHERE bucket=%s',('ai-user:'+str(row[0]),))
            conn.execute('DELETE FROM knowledgeai_v1.users WHERE email IN (%s,%s)',tuple(emails))
        print('Fictional account cleanup: PASS',flush=True)
    print('CLOUD API INTEGRATION: PASS (simulated AI, real PostgreSQL)')

if __name__=='__main__':
    try: main()
    except Exception as exc:
        print('API CHECK FAILED:',type(exc).__name__,file=sys.stderr)
        sys.exit(1)
