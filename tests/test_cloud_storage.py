import copy
import hashlib
import secrets
import pytest
from backend.cloud_storage import (normalize_email, hash_password, verify_password, token_digest,
                                   validate_chunks, validate_url, MODEL)


def sample():
    source='example.txt'
    return [dict(source=source, document_id=hashlib.sha256(source.encode()).hexdigest()[:32],
                 document_sha256='a'*64, embedding_model=MODEL, chunk_number=1, start=0,
                 end=4, text='test', vector=[1.0]+[0.0]*383)]


def test_password_roundtrip_and_salt():
    pw='fictional-password-123'
    a,b=hash_password(pw),hash_password(pw)
    assert a!=b and pw not in a and verify_password(pw,a)
    assert not verify_password('wrong-password-123',a)
    assert not verify_password(pw,'malformed')

@pytest.mark.parametrize('pw',['','short', 'x'*129, None])
def test_invalid_password(pw):
    with pytest.raises(ValueError): hash_password(pw)


def test_email():
    assert normalize_email(' Test@Example.Invalid ')=='test@example.invalid'

@pytest.mark.parametrize('email',['x','x@','x@y','x\n@y.com',None])
def test_invalid_email(email):
    with pytest.raises(ValueError): normalize_email(email)


def test_session_digest():
    t=secrets.token_urlsafe(32)
    assert token_digest(t)==hashlib.sha256(t.encode()).hexdigest()
    with pytest.raises(ValueError): token_digest('short')


def test_document():
    c=sample()
    assert validate_chunks(c)==(c[0]['source'],c[0]['document_id'],c[0]['document_sha256'])

@pytest.mark.parametrize('key,value',[('vector',[0.0]*384),('vector',[float('nan')]*384),('vector',[1.0]),('embedding_model','local'),('source','../unsafe.txt'),('document_id','wrong'),('document_sha256','wrong'),('chunk_number',2),('text',''),('start',-1),('end',801)])
def test_invalid_chunk(key,value):
    c=sample(); c[0][key]=value
    with pytest.raises(ValueError): validate_chunks(c)


def test_url():
    url='postgresql://example:fictional@ep-example-pooler.example.neon.tech/neondb?sslmode=require'
    assert validate_url("psql '"+url+"'")==url

@pytest.mark.parametrize('url',['', 'postgresql://x:p@other.example/neondb?sslmode=require','postgresql://x:p@ep-example.neon.tech/neondb?sslmode=require','postgresql://x:***@ep-example-pooler.neon.tech/neondb?sslmode=require','postgresql://x:p@ep-example-pooler.neon.tech/other?sslmode=require','postgresql://x:p@ep-example-pooler.neon.tech/neondb?sslmode=disable'])
def test_invalid_url(url):
    with pytest.raises(ValueError): validate_url(url)
