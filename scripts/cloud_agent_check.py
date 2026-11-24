"""Migrate Agent Studio and verify with real PostgreSQL and simulated AI."""
import json
import secrets
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit
from fastapi.testclient import TestClient
from backend.cloud_storage import CloudStorage,validate_url
from backend.cloud_limits import CloudLimits
from backend.cloud_agents import create_agent_app

ORIGIN='https://knowledgeai.example.invalid'
H={'Origin':ORIGIN}
P='/api/cloud/agents'
BODY={'title':'Fictional study report','text':'A sample note about relational databases.','numbers':[2,4,6],'consent':True}
class SimulatedAI:
    def chat(self,messages,**kwargs): return 'Fictional database summary.'
class SimulatedCore:
    ai=SimulatedAI()

def check(condition,label):
    if not condition: raise RuntimeError(label)
    print(label+': PASS',flush=True)

def main():
    payload=json.load(sys.stdin)
    owner_url=validate_url(payload['owner']); runtime_url=validate_url(payload['runtime'])
    a,b=map(urlsplit,(owner_url,runtime_url))
    if not (a.hostname==b.hostname and a.hostname.startswith('ep-mute-art-') and a.username=='neondb_owner' and b.username=='knowledgeai_runtime'):
        raise ValueError('Wrong database credentials')
    admin,store=CloudStorage(owner_url),CloudStorage(runtime_url)
    with admin.connect() as conn:
        check(conn.execute('SELECT current_user,current_database()').fetchone()==('neondb_owner','neondb'),'Owner identity')
        conn.execute('SELECT pg_advisory_xact_lock(821642905)')
        check(conn.execute('SELECT version FROM knowledgeai_v1.schema_version').fetchall()==[(1,)],'Base schema')
        check(conn.execute("SELECT to_regclass('knowledgeai_v1.conversations') IS NOT NULL").fetchone()[0],'Conversation schema present')
        sql=(Path(__file__).resolve().parents[1]/'backend/cloud_agents.sql').read_text(encoding='utf-8')
        conn.execute(sql); conn.execute(sql)
    print('Agent migration and repeat verification: PASS')
    with store.connect() as conn:
        check(conn.execute('SELECT current_user').fetchone()==('knowledgeai_runtime',),'Restricted runtime identity')
        check(not conn.execute("SELECT has_table_privilege(current_user,'knowledgeai_v1.agent_runs','TRUNCATE') OR has_column_privilege(current_user,'knowledgeai_v1.agent_runs','draft','UPDATE') OR has_column_privilege(current_user,'knowledgeai_v1.agent_runs','user_id','UPDATE')").fetchone()[0],'Restricted agent grants')
    tag=uuid.uuid4().hex
    creds=[{'email':f'agent-{tag}-{i}@example.invalid','password':secrets.token_urlsafe(24)} for i in range(2)]
    app=create_agent_app(store,SimulatedCore(),CloudLimits(store),ORIGIN)
    x,y=[TestClient(app,base_url=ORIGIN,raise_server_exceptions=False) for _ in range(2)]
    def create(client):
        r=client.post(P,json=BODY,headers=H)
        if r.status_code==429: raise RuntimeError('Daily budget reached; retry after UTC reset')
        check(r.status_code==201,'Create private draft')
        return P+'/'+r.json()['id']
    try:
        check(x.get(P).status_code==401,'Unauthenticated access blocked')
        for client,c in zip((x,y),creds):
            store.create_user(c['email'],c['password'])
            check(client.post('/api/cloud/login',json=c,headers=H).status_code==200,'Fictional login')
        check(x.post(P,json=BODY|{'consent':False},headers=H).status_code==422,'Explicit consent')
        p=create(x)
        check('Average of 3 supplied numbers: 4.0' in x.get(p).json()['draft'],'Deterministic calculation')
        check(x.get(p+'/report').status_code==409,'Unapproved download blocked')
        check(y.get(P).json()=={'workflows':[]} and y.get(p).status_code==404 and y.get(p+'/report').status_code==404,'Cross-user reads blocked')
        check(y.post(p+'/decision',json={'approve':True},headers=H).status_code==404 and y.delete(p,headers=H).status_code==404,'Cross-user writes blocked')
        check(x.post(p+'/decision',json={'approve':True},headers=H).json().get('status')=='approved','Owner approval')
        check(x.post(p+'/decision',json={'approve':False},headers=H).status_code==409,'Repeated decision blocked')
        check(x.post('/api/cloud/logout',json={},headers=H).status_code==200,'Logout')
        z=TestClient(create_agent_app(CloudStorage(runtime_url),SimulatedCore(),CloudLimits(CloudStorage(runtime_url)),ORIGIN),base_url=ORIGIN,raise_server_exceptions=False)
        check(z.post('/api/cloud/login',json=creds[0],headers=H).status_code==200,'Fresh application login')
        report=z.get(p+'/report')
        check(report.status_code==200 and 'attachment' in report.headers.get('content-disposition','') and 'Fictional database summary.' in report.text,'Approved report persists and downloads')
        p2=create(z)
        check(z.post(p2+'/decision',json={'approve':False},headers=H).json().get('status')=='rejected' and z.get(p2+'/report').status_code==409,'Rejected download blocked')
        p3=create(z)
        with admin.connect() as conn:
            conn.execute("UPDATE knowledgeai_v1.agent_runs SET expires_at=now()-interval '1 second' WHERE id=%s AND user_id=(SELECT id FROM knowledgeai_v1.users WHERE email=%s)",(uuid.UUID(p3.rsplit('/',1)[1]),creds[0]['email']))
        check(z.get(p3).json().get('status')=='expired' and z.post(p3+'/decision',json={'approve':True},headers=H).status_code==409 and z.get(p3+'/report').status_code==409,'Expired workflow blocked')
        check(z.delete(p,headers=H).status_code==200 and z.get(p).status_code==404,'Owner deletion')
    finally:
        with admin.connect() as conn:
            emails=tuple(c['email'] for c in creds)
            rows=conn.execute('SELECT id FROM knowledgeai_v1.users WHERE email IN (%s,%s)',emails).fetchall()
            for (uid,) in rows: conn.execute('DELETE FROM knowledgeai_v1.request_budgets WHERE bucket=%s',('ai-user:'+str(uid),))
            conn.execute('DELETE FROM knowledgeai_v1.users WHERE email IN (%s,%s)',emails)
        print('Fictional account cleanup: PASS')
    print('CLOUD AGENT STUDIO: PASS (simulated AI, real PostgreSQL)')

if __name__=='__main__':
    try: main()
    except Exception as exc:
        # Only allow our own fixed diagnostic through; never print DB error details.
        print('AGENT CHECK FAILED:',type(exc).__name__,file=sys.stderr)
        if type(exc) is RuntimeError and str(exc)=='Daily budget reached; retry after UTC reset':
            print('Daily budget reached; retry after UTC reset',file=sys.stderr)
        sys.exit(1)
