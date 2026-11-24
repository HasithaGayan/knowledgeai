"""Apply schema v1 and check persistence with disposable fictional accounts.
Run only against the dedicated KnowledgeAI Neon project. Read URL from stdin.
No real documents, credentials or session tokens are printed or stored in files.
"""
import hashlib
import secrets
import sys
import uuid

from backend.cloud_storage import CloudStorage, MODEL, token_digest


def require(condition, name):
    if not condition:
        raise RuntimeError(name)
    print(name + ': PASS', flush=True)


def sample(text):
    filename = 'fictional.txt'
    return [dict(source=filename, document_id=hashlib.sha256(filename.encode()).hexdigest()[:32],
                 document_sha256=hashlib.sha256(text.encode()).hexdigest(), embedding_model=MODEL,
                 chunk_number=1, start=0, end=len(text), text=text, vector=[1.0]+[0.0]*383)]


def main():
    store = CloudStorage(sys.stdin.read())
    store.migrate()
    store.migrate()
    print('Schema migration and repeat verification: PASS', flush=True)
    marker = uuid.uuid4().hex
    email_a, email_b = [f'storage-{marker}-{x}@example.invalid' for x in ('a','b')]
    password = secrets.token_urlsafe(24)
    try:
        a = store.create_user(email_a, password)
        b = store.create_user(email_b, password)
        require(a != b and store.authenticate(email_a, password) == a and
                store.authenticate(email_b, password) == b and
                store.authenticate(email_a, 'incorrect-password') is None and
                store.authenticate('missing@example.invalid', password) is None, 'Account authentication')
        with store.connect() as conn:
            row = conn.execute('SELECT password_hash FROM knowledgeai_v1.users WHERE id=%s',(a,)).fetchone()
            require(row[0].startswith('scrypt1$') and password not in row[0], 'Password hashing')
        token_a, token_b = store.issue_session(a), store.issue_session(b)
        require(store.session_owner(token_a)==a and store.session_owner(token_b)==b and store.session_owner('bad') is None, 'Session ownership')
        with store.connect() as conn:
            row = conn.execute('SELECT token_hash FROM knowledgeai_v1.sessions WHERE user_id=%s',(a,)).fetchone()
            require(row[0]==token_digest(token_a) and row[0]!=token_a, 'Session token hashing')
        doc = store.save_document(a, sample('Fictional A document.'))
        # New connections are created for every method; no in-memory document index.
        require(store.load_chunks(a)[0]['text']=='Fictional A document.' and
                store.list_documents(a)==[dict(document_id=doc,source='fictional.txt')], 'Persistent document and vector')
        require(store.list_documents(b)==[] and store.load_chunks(b)==[] and not store.delete_document(b, doc), 'Cross-user isolation')
        require(store.save_document(b, sample('Fictional B document.')) == doc and
                store.load_chunks(b)[0]['text']=='Fictional B document.' and
                store.load_chunks(a)[0]['text']=='Fictional A document.', 'Same filename isolated by owner')
        require(store.delete_document(a, doc) and store.load_chunks(a)==[] and len(store.load_chunks(b))==1, 'Owner-only deletion and cascade')
        store.revoke_session(token_a)
        require(store.session_owner(token_a) is None and store.session_owner(token_b)==b, 'Session revocation')
        with store.connect() as conn:
            conn.execute("UPDATE knowledgeai_v1.sessions SET expires_at=now()-interval '1 minute' WHERE token_hash=%s", (token_digest(token_b),))
        require(store.session_owner(token_b) is None, 'Session expiry')
    finally:
        with store.connect() as conn:
            conn.execute('DELETE FROM knowledgeai_v1.users WHERE email IN (%s,%s)', (email_a,email_b))
            remaining = conn.execute('SELECT count(*) FROM knowledgeai_v1.users WHERE email IN (%s,%s)', (email_a,email_b)).fetchone()[0]
            require(remaining==0, 'Fictional account cleanup')
    print('KNOWLEDGEAI STORAGE FOUNDATION: PASS')


if __name__=='__main__':
    try:
        main()
    except Exception as exc:
        # Database errors can include connection metadata or user data.
        print('STORAGE CHECK FAILED:',type(exc).__name__, file=sys.stderr)
        sys.exit(1)
