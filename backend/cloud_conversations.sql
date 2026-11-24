CREATE TABLE IF NOT EXISTS knowledgeai_v1.conversations (
    user_id uuid NOT NULL REFERENCES knowledgeai_v1.users(id) ON DELETE CASCADE,
    id uuid NOT NULL,
    title varchar(80) NOT NULL CHECK (char_length(title) BETWEEN 1 AND 80),
    revision integer NOT NULL DEFAULT 0 CHECK (revision BETWEEN 0 AND 10),
    messages jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(messages)='array' AND jsonb_array_length(messages)=revision*2),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id,id)
);
GRANT SELECT, INSERT, DELETE, UPDATE (messages,revision,updated_at) ON knowledgeai_v1.conversations TO knowledgeai_runtime;
