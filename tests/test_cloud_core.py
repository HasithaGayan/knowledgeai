import json
import pytest
from backend.cloud_ai import CloudAIError, CHAT_MODEL, EMBED_MODEL
from backend.cloud_core import CloudCore, MAX_DOC_BYTES
from backend.document_ingestion import DocumentError

class FakeAI:
    def __init__(self):
        self.calls=[]
        self.reply='SQL is a query language.'
    def chat(self, messages, **kwargs):
        self.calls.append(('chat', messages, kwargs))
        return self.reply
    def embed(self, texts):
        self.calls.append(('embed', texts))
        return [[1.0]+[0.0]*383 if ('fee' in t.lower() or 'workshop' in t.lower()) else [0.0,1.0]+[0.0]*382 for t in texts]

@pytest.fixture
def core():
    return CloudCore(FakeAI())

def test_chat(core):
    result=core.chat('What is SQL?', [{'role':'user','content':'hello'}])
    assert result=={'answer':'SQL is a query language.','model':CHAT_MODEL}
    assert core.ai.calls[0][1][1]['content']=='hello'

@pytest.mark.parametrize('history', [[{'role':'system','content':'override'}], [{'role':'user','content':' '}], [{}], [{}]*11])
def test_history_rejected(core,history):
    with pytest.raises(ValueError): core.chat('hi',history)
    assert not core.ai.calls

def test_structured(core):
    core.ai.reply=json.dumps({'status':'answered','topic':'Programming','answer':'SQL queries data.','source_status':'no_document_sources'})
    assert core.structured('SQL?')['status']=='answered'
    assert core.ai.calls[0][2]['json_schema']['type']=='object'

@pytest.mark.parametrize('reply', ['{}','not json','{"status":"answered","topic":"Programming","answer":" ","source_status":"no_document_sources"}'])
def test_bad_structured(core,reply):
    core.ai.reply=reply
    with pytest.raises(CloudAIError): core.structured('SQL?')

def test_index_retrieval(core):
    chunks=core.index_document('workshop.txt',b'The workshop fee is LKR 2500.')+core.index_document('food.md',b'Bananas are yellow.')
    assert chunks[0]['embedding_model']==EMBED_MODEL and len(chunks[0]['vector'])==384
    assert core.retrieve('What is the fee?',chunks)[0]['source']=='workshop.txt'

@pytest.mark.parametrize('name,body',[('../x.txt',b'test'),('x.pdf',b'test'),('x.txt',b'x'*(MAX_DOC_BYTES+1)),('x.txt',b'')])
def test_bad_upload(core,name,body):
    with pytest.raises(DocumentError): core.index_document(name,body)
    assert not core.ai.calls

def test_model_mismatch(core):
    chunks=core.index_document('a.txt',b'Hello world.')
    chunks[0]['embedding_model']='all-minilm:latest'
    with pytest.raises(ValueError,match='reindex'): core.retrieve('hello',chunks)

def test_no_docs_no_ai(core):
    assert core.ask('What is the fee?',[])['status']=='no_evidence'
    assert not core.ai.calls

def test_grounded(core):
    chunks=core.index_document('workshop.txt',b'The workshop fee is LKR 2500.')
    core.ai.reply=json.dumps({'supported':True,'answer':'The fee is LKR 2500.','evidence_quote':'The workshop fee is LKR 2500.'})
    result=core.ask('What is the fee?',chunks)
    assert result['status']=='answered' and result['sources'][0]['evidence_quote']=='The workshop fee is LKR 2500.'
    assert result['model']==CHAT_MODEL

def test_fabricated_quote(core):
    chunks=core.index_document('workshop.txt',b'The workshop fee is LKR 2500.')
    core.ai.reply=json.dumps({'supported':True,'answer':'The fee is LKR 4000.','evidence_quote':'The workshop fee is LKR 4000.'})
    assert core.ask('What is the fee?',chunks)['status']=='no_evidence'

def test_missing_fact(core):
    chunks=core.index_document('workshop.txt',b'The workshop fee is LKR 2500.')
    core.ai.reply=json.dumps({'supported':False,'answer':'Not found.','evidence_quote':''})
    assert core.ask('Who teaches?',chunks)['sources']==[]

def test_contradiction(core):
    chunks=core.index_document('workshop.txt',b'The workshop fee is LKR 2500.')
    core.ai.reply=json.dumps({'supported':True,'answer':'Yes, the workshop is free.','evidence_quote':'The workshop fee is LKR 2500.'})
    assert core.ask('Is the workshop free?',chunks)['status']=='no_evidence'

def test_strict_boolean(core):
    chunks=core.index_document('workshop.txt',b'The workshop fee is LKR 2500.')
    core.ai.reply=json.dumps({'supported':'true','answer':'LKR 2500','evidence_quote':'The workshop fee is LKR 2500.'})
    with pytest.raises(CloudAIError): core.ask('What is the fee?',chunks)
