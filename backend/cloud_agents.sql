CREATE TABLE IF NOT EXISTS knowledgeai_v1.agent_runs (
    user_id uuid NOT NULL REFERENCES knowledgeai_v1.users(id) ON DELETE CASCADE,
    id uuid NOT NULL,
    title varchar(100) NOT NULL,
    draft text NOT NULL CHECK (char_length(draft) BETWEEN 1 AND 5000),
    trace jsonb NOT NULL CHECK (jsonb_typeof(trace) = 'array'),
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL DEFAULT (now() + interval '1 hour'),
    PRIMARY KEY (user_id,id)
);
GRANT SELECT, INSERT, DELETE, UPDATE (status) ON knowledgeai_v1.agent_runs TO knowledgeai_runtime;
