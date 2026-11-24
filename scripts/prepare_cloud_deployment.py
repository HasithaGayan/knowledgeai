"""Build a cloud-only local staging directory from committed KnowledgeAI sources.
No deploy, database connection, or AI request is performed.
"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import shutil
import json

FILES = tuple('backend/' + name + '.py' for name in (
    'cloud_ai', 'cloud_core', 'cloud_storage', 'cloud_limits', 'cloud_api',
    'cloud_conversations', 'cloud_agents', 'cloud_web', 'document_ingestion',
    'rag_assistant', 'structured_output', 'evidence_alignment',
    'grounded_recovery', 'safe_citation_fallback', 'safe_tools',
    'answer_guard', 'conversation_stream', 'semantic_retrieval',
)) + ('frontend/cloud.html', 'frontend/cloud.css', 'frontend/cloud.js')

MAIN = '''"""Vercel cloud-only application. No migrations or local routes on startup."""
import os
import re
from urllib.parse import urlsplit
from backend.cloud_ai import CloudAI
from backend.cloud_core import CloudCore
from backend.cloud_storage import CloudStorage, validate_url
from backend.cloud_limits import CloudLimits
from backend.cloud_web import create_web_app


def build_app(env):
    try:
        raw = env['KNOWLEDGEAI_DATABASE_URL']
        origin = env['KNOWLEDGEAI_PUBLIC_ORIGIN']
        account = env['CLOUDFLARE_ACCOUNT_ID']
        token = env['CLOUDFLARE_API_TOKEN']
        url = validate_url(raw)
        p = urlsplit(url)
        if raw != url or p.username != 'knowledgeai_runtime' or not p.hostname.startswith('ep-mute-art-'):
            raise ValueError('Wrong runtime identity')
        if not re.fullmatch(r'https://[a-z0-9][a-z0-9-]*\\.vercel\\.app', origin):
            raise ValueError('Expected canonical Vercel HTTPS origin')
        store = CloudStorage(url)
        core = CloudCore(CloudAI(account, token))
        return create_web_app(store, core, CloudLimits(store), origin)
    except (KeyError, ValueError, TypeError):
        raise RuntimeError('Missing or invalid KnowledgeAI production configuration') from None


app = build_app(os.environ)
'''

CHECK = '''import os
from fastapi.testclient import TestClient
from main import app, build_app
base = dict(os.environ)
for name in ('KNOWLEDGEAI_DATABASE_URL','KNOWLEDGEAI_PUBLIC_ORIGIN','CLOUDFLARE_ACCOUNT_ID','CLOUDFLARE_API_TOKEN'):
    bad = dict(base); bad.pop(name)
    try: build_app(bad)
    except RuntimeError: pass
    else: raise AssertionError('Missing configuration accepted')
for key, value in [('KNOWLEDGEAI_DATABASE_URL',base['KNOWLEDGEAI_DATABASE_URL'].replace('knowledgeai_runtime','neondb_owner')), ('KNOWLEDGEAI_PUBLIC_ORIGIN','http://localhost:8443'), ('KNOWLEDGEAI_PUBLIC_ORIGIN','https://test.vercel.app/path')]:
    bad = dict(base); bad[key] = value
    try: build_app(bad)
    except RuntimeError: pass
    else: raise AssertionError('Unsafe configuration accepted')
print('Missing or unsafe production configuration rejected: PASS')
c = TestClient(app,base_url=base['KNOWLEDGEAI_PUBLIC_ORIGIN'])
for route in ('/', '/assets/cloud.css','/assets/cloud.js','/api/cloud/health'):
    r = c.get(route); assert r.status_code == 200 and r.headers['cache-control'] == 'no-store', route
assert "frame-ancestors 'none'" in c.get('/').headers['content-security-policy']
print('Cloud frontend, health and security headers: PASS')
for route in ('/api/cloud/me','/api/cloud/documents','/api/cloud/conversations','/api/cloud/agents'):
    assert c.get(route).status_code == 401, route
assert c.post('/api/cloud/login',json={'email':'test@example.com','password':'fictional-only-password'},headers={'Origin':'https://other.example'}).status_code == 403
for route in ('/docs','/openapi.json','/workspace','/backend/cloud_storage.py','/.env','/data/day74_conversations.sqlite3'):
    assert c.get(route).status_code == 404, route
print('Anonymous access, foreign origin and legacy/private paths blocked: PASS')
'''


def git(*args):
    return subprocess.check_output(['git', *args])


def main():
    root = Path.cwd()
    if root.name != 'knowledgeai-cloud' or git('branch','--show-current').decode().strip() != 'deploy/knowledgeai-cloud':
        raise RuntimeError('Run from the knowledgeai-cloud branch')
    if git('status','--porcelain').strip():
        raise RuntimeError('Working directory must be clean')
    head = git('rev-parse','HEAD').decode().strip()
    destination = root.parent / 'knowledgeai-vercel-staging'
    if destination.exists():
        raise RuntimeError('Staging directory already exists; no files overwritten')
    with tempfile.TemporaryDirectory(prefix='knowledgeai-stage-',dir=root.parent) as temp:
        stage = Path(temp) / 'bundle'
        stage.mkdir()
        for name in FILES:
            target = stage / name
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(git('show',f'{head}:{name}'))
        (stage/'main.py').write_text(MAIN,encoding='utf-8')
        (stage/'requirements.txt').write_text('fastapi==0.165.0\nhttpx==0.28.1\npsycopg[binary]==3.3.9\nuvicorn==0.54.0\n',encoding='utf-8')
        (stage/'.python-version').write_text('3.14\n',encoding='utf-8')
        (stage/'vercel.json').write_text(json.dumps({'framework':'fastapi','regions':['sin1']},indent=2)+'\n',encoding='utf-8')
        # Fake credentials only. No real connections are needed for these routes.
        env = dict(os.environ)
        env.update(KNOWLEDGEAI_DATABASE_URL='postgresql://knowledgeai_runtime:fictional@ep-mute-art-offline-pooler.neon.tech/neondb?sslmode=require', KNOWLEDGEAI_PUBLIC_ORIGIN='https://offline-check.vercel.app', CLOUDFLARE_ACCOUNT_ID='0'*32, CLOUDFLARE_API_TOKEN='fictional-offline-token')
        env['PYTHONDONTWRITEBYTECODE']='1'
        # Explicitly block outgoing sockets during preflight, including regressions.
        guard = r'''import socket
import threading
_original_pair = socket.socketpair
_original_connect = socket.socket.connect
_pair_context = threading.local()

def deny(*args, **kwargs):
    raise AssertionError("External network is disabled for preflight")

def guarded_pair(*args, **kwargs):
    previous = getattr(_pair_context, "active", False)
    _pair_context.active = True
    try:
        return _original_pair(*args, **kwargs)
    finally:
        _pair_context.active = previous

def guarded_connect(sock, address):
    # Windows implements socketpair with a temporary loopback TCP listener.
    # Permit only that internal call, in the same thread, to numeric loopback.
    if (getattr(_pair_context, "active", False)
            and isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1")):
        return _original_connect(sock, address)
    return deny()

socket.socketpair = guarded_pair
socket.socket.connect = guarded_connect
socket.socket.connect_ex = deny
socket.create_connection = deny
# libpq uses native sockets, so block its Python entry point as well.
try:
    import psycopg
except ModuleNotFoundError as exc:
    if exc.name != "psycopg":
        raise
else:
    psycopg.connect = deny
# Verify that the internal pair works and ordinary connections remain blocked.
with socket.socket() as probe:
    for address in (("127.0.0.1", 9), ("192.0.2.1", 443)):
        try:
            probe.connect(address)
        except AssertionError:
            pass
        else:
            raise AssertionError("Unexpected connection allowed")
a, b = socket.socketpair()
with a, b:
    a.sendall(b"x")
    assert b.recv(1) == b"x"
print("Offline network guard: PASS", flush=True)
'''
        subprocess.run([sys.executable,'-c',guard+CHECK],cwd=stage,env=env,check=True)
        print('Allowlisted committed runtime source files:',len(FILES))
        print('Source commit:',head[:7])
        shutil.move(str(stage),str(destination))
    print('Staging directory:',destination)
    print('KNOWLEDGEAI OFFLINE DEPLOYMENT PREPARATION: PASS')
    print('No credentials copied, AI calls made, database writes or deployment performed.')

if __name__=='__main__':
    try:
        main()
    except Exception as exc:
        print('PREPARATION STOPPED:', type(exc).__name__)
        if isinstance(exc,RuntimeError): print(str(exc))
        sys.exit(1)
