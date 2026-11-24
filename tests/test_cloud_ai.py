import json
import httpx
import pytest
from backend.cloud_ai import CloudAI, CloudAIError, CHAT_MODEL, EMBED_MODEL


def provider(handler):
    return CloudAI('a'*32, 'test-only-token', transport=httpx.MockTransport(handler))


def test_chat_messages_and_limits():
    def handler(req):
        assert req.url.path.endswith(CHAT_MODEL)
        assert req.headers['authorization'] == 'Bearer test-only-token'
        body = json.loads(req.content)
        assert body['messages'] == [{'role':'user','content':'What is SQL?'}]
        assert body['temperature'] == 0.2 and body['stream'] is False
        return httpx.Response(200, json={'success': True, 'result': {'response':' SQL is a query language. '}})
    assert provider(handler).chat([{'role':'user','content':'What is SQL?'}]) == 'SQL is a query language.'


def test_embedding():
    def handler(req):
        assert req.url.path.endswith(EMBED_MODEL)
        assert json.loads(req.content) == {'text':['a','b']}
        return httpx.Response(200, json={'success':True,'result':{'data':[[0.1]*384,[0.2]*384]}})
    assert len(provider(handler).embed(['a','b'])[0]) == 384


@pytest.mark.parametrize('status', [401, 429, 500, 302])
def test_status(status):
    with pytest.raises(CloudAIError, match=f'HTTP {status}') as exc:
        provider(lambda req: httpx.Response(status, text='test-only-token')).chat([{'role':'user','content':'hi'}])
    assert 'test-only-token' not in str(exc.value)


@pytest.mark.parametrize('body', [{}, {'success':False,'result':{}}, {'success':True,'result':{'response':' '}}])
def test_invalid_chat(body):
    with pytest.raises(CloudAIError):
        provider(lambda req: httpx.Response(200,json=body)).chat([{'role':'user','content':'hi'}])


@pytest.mark.parametrize('vectors', [[], [[1.0]*383], [[0.0]*384], [[True]*384]])
def test_invalid_embedding(vectors):
    with pytest.raises(CloudAIError):
        provider(lambda req: httpx.Response(200,json={'success':True,'result':{'data':vectors}})).embed(['a'])


def test_invalid_input():
    p = provider(lambda req: pytest.fail('network must not be called'))
    with pytest.raises(ValueError): p.chat([{'role':'user','content':' '}])
    with pytest.raises(ValueError): p.embed(['a']*17)


def test_timeout():
    def handler(req): raise httpx.ReadTimeout('test-only-token',request=req)
    with pytest.raises(CloudAIError, match='network or response failure'):
        provider(handler).chat([{'role':'user','content':'hi'}])


@pytest.mark.parametrize('response', [{'answer':'9 AM','source':'S1'}, '{"answer":"9 AM","source":"S1"}'])
def test_structured_response(response):
    schema = {'type':'object', 'properties':{'answer':{'type':'string'}}}
    def handler(req):
        body = json.loads(req.content)
        assert body['response_format'] == {'type':'json_schema','json_schema':schema}
        assert body['repetition_penalty'] == 1.1
        return httpx.Response(200,json={'success':True,'result':{'response':response}})
    assert json.loads(provider(handler).chat([{'role':'user','content':'Return JSON'}],json_schema=schema)) == {'answer':'9 AM','source':'S1'}

@pytest.mark.parametrize('response', [None, '', 'not JSON', [], {}, '[]'])
def test_reject_invalid_structured_response(response):
    p = provider(lambda req: httpx.Response(200,json={'success':True,'result':{'response':response}}))
    with pytest.raises(CloudAIError):
        p.chat([{'role':'user','content':'Return JSON'}],json_schema={'type':'object'})
