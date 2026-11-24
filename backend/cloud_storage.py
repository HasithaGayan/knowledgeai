"""Cloud persistence foundation. No public HTTP routes.
Owner IDs must come from verified server sessions, never request bodies.
The database owner is for migration/testing only; runtime grants come later.
"""
from __future__ import annotations

import hashlib
import hmac
import math
import re
import secrets
import uuid
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

MODEL = '@cf/baai/bge-small-en-v1.5'
DIM = 384
MAX_DOCUMENTS = 8
MAX_CHUNKS = 128
SESSION_DAYS = 7


def validate_url(raw: str) -> str:
    match = re.search(r"postgres(?:ql)?://[^\s'\"<>]+", raw.strip())
    if not match:
        raise ValueError('Missing database URL')
    url = match.group(0)
    p = urlsplit(url)
    if (not p.hostname or not p.hostname.endswith('.neon.tech') or '-pooler' not in p.hostname
        or p.path != '/neondb' or not p.password or '*' in p.password
        or parse_qs(p.query).get('sslmode') not in (['require'], ['verify-ca'], ['verify-full'])):
        raise ValueError('Expected pooled Neon database URL with TLS')
    return url


def normalize_email(email: str) -> str:
    if not isinstance(email, str):
        raise ValueError('Invalid email')
    email = email.strip().lower()
    if len(email) > 254 or not re.fullmatch(r'[a-z0-9.!#$%&*+/=?^_`{|}~-]{1,64}@[a-z0-9-]+(?:\.[a-z0-9-]+)+', email):
        raise ValueError('Invalid email')
    return email


def _password_bytes(password: str) -> bytes:
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        raise ValueError('Password must have 12-128 characters')
    return password.encode('utf-8')


def _derive(password: bytes, salt: bytes) -> bytes:
    return hashlib.scrypt(password, salt=salt, n=32768, r=8, p=3, dklen=32, maxmem=64*1024*1024)


def hash_password(password: str) -> str:
    raw = _password_bytes(password)
    salt = secrets.token_bytes(16)
    return 'scrypt1$' + salt.hex() + '$' + _derive(raw, salt).hex()


def verify_password(password: str, encoded: str) -> bool:
    try:
        raw = _password_bytes(password)
        version, salt_hex, digest_hex = encoded.split('$')
        if version != 'scrypt1' or len(salt_hex) != 32 or len(digest_hex) != 64:
            return False
        return hmac.compare_digest(_derive(raw, bytes.fromhex(salt_hex)), bytes.fromhex(digest_hex))
    except (ValueError, TypeError, AttributeError):
        return False


def token_digest(token: str) -> str:
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
        raise ValueError('Invalid session')
    return hashlib.sha256(token.encode('ascii')).hexdigest()


def validate_chunks(chunks: list[dict]) -> tuple[str, str, str]:
    if not isinstance(chunks, list) or not 1 <= len(chunks) <= 16 or not all(isinstance(c, dict) for c in chunks):
        raise ValueError('Invalid document chunks')
    first = chunks[0]
    source, doc_id, sha = (first.get(k) for k in ('source', 'document_id', 'document_sha256'))
    if (not isinstance(source, str) or not 1 <= len(source) <= 120 or source.startswith('.')
        or any(c in source for c in ('/', '\\', '\x00')) or not source.lower().endswith(('.txt', '.md'))
        or doc_id != hashlib.sha256(source.encode('utf-8')).hexdigest()[:32]
        or not isinstance(sha, str) or not re.fullmatch(r'[a-f0-9]{64}', sha)):
        raise ValueError('Invalid document metadata')
    for i, c in enumerate(chunks, 1):
        v = c.get('vector')
        text, start, end = (c.get(k) for k in ('text', 'start', 'end'))
        if (c.get('source'), c.get('document_id'), c.get('document_sha256'), c.get('embedding_model'), c.get('chunk_number')) != (source, doc_id, sha, MODEL, i):
            raise ValueError('Inconsistent chunk metadata')
        if (not isinstance(text, str) or not text.strip() or len(text) > 800 or '\x00' in text
            or type(start) is not int or type(end) is not int or not 0 <= start < end <= 12000 or end-start > 800):
            raise ValueError('Invalid chunk text or offsets')
        if (not isinstance(v, list) or len(v) != DIM or not all(type(x) in (int,float) and math.isfinite(x) for x in v)
            or not 0 < math.hypot(*v) < math.inf):
            raise ValueError('Invalid vector')
    return source, doc_id, sha


class CloudStorage:
    def __init__(self, url: str):
        self._url = validate_url(url)

    def connect(self):
        import psycopg
        return psycopg.connect(self._url, connect_timeout=15, prepare_threshold=None)

    def migrate(self):
        with self.connect() as conn:
            conn.execute('SELECT pg_advisory_xact_lock(821642905)')
            exists = conn.execute("SELECT to_regnamespace('knowledgeai_v1') IS NOT NULL").fetchone()[0]
            if not exists:
                conn.execute(Path(__file__).with_name('cloud_schema.sql').read_text(encoding='utf-8'))
            if conn.execute('SELECT version FROM knowledgeai_v1.schema_version').fetchall() != [(1,)]:
                raise RuntimeError('Unexpected schema version')

    def create_user(self, email: str, password: str) -> uuid.UUID:
        email, encoded, uid = normalize_email(email), hash_password(password), uuid.uuid4()
        with self.connect() as conn:
            conn.execute('INSERT INTO knowledgeai_v1.users(id,email,password_hash) VALUES (%s,%s,%s)', (uid,email,encoded))
        return uid

    def authenticate(self, email: str, password: str) -> uuid.UUID | None:
        try:
            email = normalize_email(email)
            raw = _password_bytes(password)
        except ValueError:
            return None
        with self.connect() as conn:
            row = conn.execute('SELECT id,password_hash FROM knowledgeai_v1.users WHERE email=%s', (email,)).fetchone()
        if row is None:
            _derive(raw, bytes(16)) # reduce obvious timing differences for unknown users
            return None
        return row[0] if verify_password(password, row[1]) else None

    def issue_session(self, owner: uuid.UUID) -> str:
        token = secrets.token_urlsafe(32)
        with self.connect() as conn:
            # Serialize issuance for a user and bound the number of active sessions.
            if conn.execute('SELECT id FROM knowledgeai_v1.users WHERE id=%s FOR UPDATE', (owner,)).fetchone() is None:
                raise ValueError('Unknown owner')
            conn.execute('DELETE FROM knowledgeai_v1.sessions WHERE user_id=%s AND expires_at<=now()', (owner,))
            count = conn.execute('SELECT count(*) FROM knowledgeai_v1.sessions WHERE user_id=%s', (owner,)).fetchone()[0]
            if count >= 10:
                raise ValueError('Too many active sessions')
            conn.execute("INSERT INTO knowledgeai_v1.sessions(token_hash,user_id,expires_at) VALUES (%s,%s,now()+interval '7 days')", (token_digest(token),owner))
        return token

    def session_owner(self, token: str) -> uuid.UUID | None:
        try:
            digest = token_digest(token)
        except ValueError:
            return None
        with self.connect() as conn:
            row = conn.execute('SELECT user_id FROM knowledgeai_v1.sessions WHERE token_hash=%s AND expires_at>now()', (digest,)).fetchone()
        return row[0] if row else None

    def revoke_session(self, token: str):
        digest = token_digest(token)
        with self.connect() as conn:
            conn.execute('DELETE FROM knowledgeai_v1.sessions WHERE token_hash=%s', (digest,))

    def save_document(self, owner: uuid.UUID, chunks: list[dict]) -> str:
        from psycopg.types.json import Jsonb
        source, doc_id, sha = validate_chunks(chunks)
        with self.connect() as conn:
            if conn.execute('SELECT id FROM knowledgeai_v1.users WHERE id=%s FOR UPDATE', (owner,)).fetchone() is None:
                raise ValueError('Unknown owner')
            docs = conn.execute('SELECT count(*) FROM knowledgeai_v1.documents WHERE user_id=%s', (owner,)).fetchone()[0]
            total = conn.execute('SELECT count(*) FROM knowledgeai_v1.chunks WHERE user_id=%s', (owner,)).fetchone()[0]
            if docs >= MAX_DOCUMENTS or total + len(chunks) > MAX_CHUNKS:
                raise ValueError('Document quota exceeded')
            conn.execute('INSERT INTO knowledgeai_v1.documents(user_id,document_id,source,document_sha256,embedding_model) VALUES (%s,%s,%s,%s,%s)', (owner,doc_id,source,sha,MODEL))
            with conn.cursor() as cur:
                cur.executemany('INSERT INTO knowledgeai_v1.chunks(user_id,document_id,chunk_number,start_pos,end_pos,content,vector) VALUES (%s,%s,%s,%s,%s,%s,%s)', [(owner,doc_id,c['chunk_number'],c['start'],c['end'],c['text'],Jsonb(c['vector'])) for c in chunks])
        return doc_id

    def list_documents(self, owner: uuid.UUID) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute('SELECT document_id,source FROM knowledgeai_v1.documents WHERE user_id=%s ORDER BY source LIMIT 8', (owner,)).fetchall()
        return [dict(document_id=r[0],source=r[1]) for r in rows]

    def load_chunks(self, owner: uuid.UUID) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute('''SELECT d.document_id,d.source,d.document_sha256,d.embedding_model,c.chunk_number,c.start_pos,c.end_pos,c.content,c.vector
                FROM knowledgeai_v1.documents d JOIN knowledgeai_v1.chunks c ON (d.user_id,d.document_id)=(c.user_id,c.document_id)
                WHERE d.user_id=%s ORDER BY d.source,c.chunk_number LIMIT 129''', (owner,)).fetchall()
        if len(rows)>MAX_CHUNKS:
            raise RuntimeError('Stored chunk limit exceeded')
        keys = ('document_id','source','document_sha256','embedding_model','chunk_number','start','end','text','vector')
        return [dict(zip(keys,r)) for r in rows]

    def delete_document(self, owner: uuid.UUID, doc_id: str) -> bool:
        with self.connect() as conn:
            return conn.execute('DELETE FROM knowledgeai_v1.documents WHERE user_id=%s AND document_id=%s', (owner,doc_id)).rowcount == 1
