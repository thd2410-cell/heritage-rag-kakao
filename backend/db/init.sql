CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;

CREATE TABLE IF NOT EXISTS heritages (
    id BIGSERIAL PRIMARY KEY,
    ccba_kdcd TEXT NOT NULL,
    ccba_asno TEXT NOT NULL,
    ccba_ctcd TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT,
    region TEXT,
    era TEXT,
    address TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    image_url TEXT,
    content TEXT,
    source_url TEXT,
    facet_json JSONB,
    raw_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (ccba_kdcd, ccba_asno, ccba_ctcd)
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id BIGSERIAL PRIMARY KEY,
    heritage_id BIGINT NOT NULL REFERENCES heritages(id) ON DELETE CASCADE,
    chunk_text TEXT NOT NULL,
    embedding vector(1024),
    metadata_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding
ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE TABLE IF NOT EXISTS chat_logs (
    id BIGSERIAL PRIMARY KEY,
    user_key TEXT,
    utterance TEXT NOT NULL,
    answer TEXT NOT NULL,
    sources JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
