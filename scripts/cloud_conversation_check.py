"""One-time migration and real PostgreSQL / simulated AI integration check."""
import json
import secrets
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit
from fastapi.testclient import TestClient
from backend.cloud_storage import CloudStorage, validate_url
from backend.cloud_limits import CloudLimits
from backend.cloud_conversations import create_conversation_app

ORIGIN='https://knowledgeai.example.invalid'
H={'Origin':ORIGIN}
P='/api/cloud/conversations'

class SimulatedCore:
    def chat(self,message,history=()):
        return {'answer': 'Previous: '+history[-2]['content'] if history else 'First answer', 'model':'simulated'}

def check(condition,label):
    if not condition: raise RuntimeError(label)
    print(label+': PASS',flush=True)

def main():
    data=json.load(sys.stdin)
    owner_url=validate_url(data['owner']); runtime_url=validate_url(data['runtime'])
    a,b=map(urlsplit,(owner_url,runtime_url))
    if not (a.hostname==b.hostname and a.hostname.startswith('ep-mute-art-') and a.username=='neondb_owner' and b.username=='knowledgeai_runtime'):
        raise ValueError('Wrong database credentials')
    admin,store=CloudStorage(owner_url),CloudStorage(runtime_url)
    with admin.connect() as conn:
        check(conn.execute('SELECT current_user,current_database()').fetchone()==('neondb_owner','neondb'),'Owner identity')
        conn.execute('SELECT pg_advisory_xact_lock(821642905)')
        check(conn.execute('SELECT version FROM knowledgeai_v1.schema_version').fetchall()==[(1,)],'Base schema')
        conn.execute((Path(__file__).resolve().parents[1]/'backend/cloud_conversations.sql').read_text(encoding='utf-8'))
    print('Conversation migration: PASS')
    with store.connect() as conn:
        check(conn.execute('SELECT current_user').fetchone()==('knowledgeai_runtime',),'Restricted runtime identity')
        check(not conn.execute("SELECT has_table_privilege(current_user,'knowledgeai_v1.conversations','TRUNCATE') OR has_column_privilege(current_user,'knowledgeai_v1.conversations','user_id','UPDATE')").fetchone()[0],'Restricted conversation grants')
    tag=uuid.uuid4().hex
    creds=[{'email':f'conversation-{tag}-{i}@example.invalid','password':secrets.token_urlsafe(24)} for i in range(2)]
    app=create_conversation_app(store,SimulatedCore(),CloudLimits(store),ORIGIN)
    x,y=[TestClient(app,base_url=ORIGIN,raise_server_exceptions=False) for _ in range(2)]
    try:
        check(x.get(P).status_code==401,'Unauthenticated access blocked')
        for client,c in zip((x,y),creds):
            store.create_user(c['email'],c['password'])
            check(client.post('/api/cloud/login',json=c,headers=H).status_code==200,'Fictional login')
        r=x.post(P,json={'title':'Fictional private chat'},headers=H)
        check(r.status_code==201,'Conversation creation'); path=P+'/'+r.json()['id']
        check(y.get(P).json()=={'conversations':[]},'Owner-only list')
        check(y.get(path).status_code==404 and y.delete(path,headers=H).status_code==404,'Cross-user read and delete denied')
        body={'message':'Fictional context','consent':True}
        check(y.post(path+'/messages',json=body,headers=H).status_code==404,'Cross-user append denied')
        check(x.post(path+'/messages',json=body|{'consent':False},headers=H).status_code==422,'Explicit consent')
        check(x.post(path+'/messages',json=body,headers=H).status_code==200,'First saved turn')
        check(x.post('/api/cloud/logout',json={},headers=H).status_code==200,'Logout')
        z=TestClient(create_conversation_app(CloudStorage(runtime_url),SimulatedCore(),CloudLimits(CloudStorage(runtime_url)),ORIGIN),base_url=ORIGIN,raise_server_exceptions=False)
        check(z.post('/api/cloud/login',json=creds[0],headers=H).status_code==200,'Fresh application login')
        check(z.get(path).json()['messages'][0]['content']=='Fictional context','History persists after new application and login')
        r=z.post(path+'/messages',json={'message':'Follow-up','consent':True},headers=H)
        check(r.status_code==200 and r.json()['answer']=='Previous: Fictional context','Server-derived history')
        check(z.get(path).json()['revision']==2,'Two stored turns')
        check(z.delete(path,headers=H).status_code==200 and z.get(path).status_code==404,'Owner deletion')
    finally:
        with admin.connect() as conn:
            emails=tuple(c['email'] for c in creds)
            rows=conn.execute('SELECT id FROM knowledgeai_v1.users WHERE email IN (%s,%s)',emails).fetchall()
            for (uid,) in rows: conn.execute('DELETE FROM knowledgeai_v1.request_budgets WHERE bucket=%s',('ai-user:'+str(uid),))
            conn.execute('DELETE FROM knowledgeai_v1.users WHERE email IN (%s,%s)',emails)
        print('Fictional account cleanup: PASS')
    print('CLOUD CONVERSATIONS: PASS (simulated AI, real PostgreSQL)')

if __name__=='__main__':
    try: main()
    except Exception as exc:
        print('CONVERSATION CHECK FAILED:',type(exc).__name__,file=sys.stderr)
        sys.exit(1)
