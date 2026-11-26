CREATE SCHEMA knowledgeai_v1;
CREATE TABLE knowledgeai_v1.schema_version (
    version integer PRIMARY KEY CHECK (version = 1)
);
INSERT INTO knowledgeai_v1.schema_version VALUES (1);
CREATE TABLE knowledgeai_v1.users (
    id uuid PRIMARY KEY,
    email varchar(254) NOT NULL UNIQUE,
    password_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE knowledgeai_v1.sessions (
    token_hash char(64) PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES knowledgeai_v1.users(id) ON DELETE CASCADE,
    expires_at timestamptz NOT NULL
);
CREATE INDEX sessions_user_idx ON knowledgeai_v1.sessions(user_id);
CREATE TABLE knowledgeai_v1.documents (
    user_id uuid NOT NULL REFERENCES knowledgeai_v1.users(id) ON DELETE CASCADE,
    document_id char(32) NOT NULL,
    source varchar(120) NOT NULL,
    document_sha256 char(64) NOT NULL,
    embedding_model text NOT NULL CHECK (embedding_model = '@cf/baai/bge-small-en-v1.5'),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, document_id),
    UNIQUE (user_id, source)
);
CREATE TABLE knowledgeai_v1.chunks (
    user_id uuid NOT NULL,
    document_id char(32) NOT NULL,
    chunk_number integer NOT NULL CHECK (chunk_number BETWEEN 1 AND 16),
    start_pos integer NOT NULL CHECK (start_pos >= 0),
    end_pos integer NOT NULL CHECK (end_pos > start_pos),
    content text NOT NULL CHECK (char_length(content) BETWEEN 1 AND 800),
    vector jsonb NOT NULL CHECK (jsonb_typeof(vector) = 'array' AND jsonb_array_length(vector) = 384),
    PRIMARY KEY (user_id, document_id, chunk_number),
    FOREIGN KEY (user_id, document_id) REFERENCES knowledgeai_v1.documents(user_id, document_id) ON DELETE CASCADE
);
