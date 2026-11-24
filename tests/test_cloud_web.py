from fastapi.testclient import TestClient
from backend.cloud_web import create_web_app
from test_cloud_api import Store, Limits, ORIGIN, HEAD, login
from test_cloud_agents import Runs, Core
from test_cloud_conversations import Conversations


def client():
    return TestClient(create_web_app(Store(),Core(),Limits(),ORIGIN,Runs(),Conversations()),base_url=ORIGIN)


def test_page_and_assets():
    c=client(); r=c.get('/')
    assert r.status_code==200 and 'KnowledgeAI' in r.text
    assert r.headers['cache-control']=='no-store'
    assert "script-src 'self'" in r.headers['content-security-policy']
    assert "frame-ancestors 'none'" in r.headers['content-security-policy']
    assert c.get('/assets/cloud.js').status_code==200
    assert c.get('/assets/cloud.css').status_code==200
    assert c.get('/backend/cloud_storage.py').status_code==404
    assert c.get('/workspace').status_code==404


def test_no_private_access_from_page():
    c=client(); assert c.get('/').status_code==200
    for route in ('me','documents','conversations','agents'):
        assert c.get('/api/cloud/'+route).status_code==401
    assert login(c).status_code==200
    assert c.get('/api/cloud/me').status_code==200
    assert c.post('/api/cloud/logout',json={},headers=HEAD).status_code==200
    assert c.get('/api/cloud/me').status_code==401
