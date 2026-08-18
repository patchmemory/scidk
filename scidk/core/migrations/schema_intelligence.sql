-- Schema Intelligence Layer Migration
-- Phases 1-3 + 6: Usage logging, property ranking, label profiles, semantic embeddings
-- Safe to run multiple times (uses IF NOT EXISTS / IF NOT EXISTS for columns)

-- Phase 1: Raw usage event log (append-only)
CREATE TABLE IF NOT EXISTS usage_event (
    id              INTEGER PRIMARY KEY,
    event_type      TEXT NOT NULL,  -- 'query_executed'
    label_name      TEXT NOT NULL,
    property_name   TEXT,           -- NULL for label-level events
    session_id      TEXT,
    source          TEXT,           -- 'chat' | 'labels_ui'
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Phase 2+3+6: Per-label enrichment, ranking, and embeddings
CREATE TABLE IF NOT EXISTS label_profile (
    id                INTEGER PRIMARY KEY,
    label_name        TEXT UNIQUE NOT NULL,
    description       TEXT,
    chat_context_mode TEXT DEFAULT 'top_n',  -- 'top_n'|'all'|'exclude'
    chat_context_n    INTEGER DEFAULT 5,
    always_include    TEXT,   -- JSON array: ["treatment", "genotype"]
    never_include     TEXT,   -- JSON array: ["_imported_stub"]
    -- Phase 6 embedding fields
    embedding         BLOB,
    embedding_model   TEXT,
    embedding_text    TEXT,
    embedded_at       DATETIME,
    created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Phase 2: Usage-weighted property ranking per label
CREATE TABLE IF NOT EXISTS property_ranking (
    id            INTEGER PRIMARY KEY,
    label_name    TEXT NOT NULL,
    property_name TEXT NOT NULL,
    query_count   INTEGER DEFAULT 0,
    session_count INTEGER DEFAULT 0,
    last_used_at  DATETIME,
    rank          REAL DEFAULT 0.0,
    UNIQUE (label_name, property_name)
);

-- Phase 6: Relationship type embeddings
CREATE TABLE IF NOT EXISTS relationship_profile (
    id              INTEGER PRIMARY KEY,
    rel_type        TEXT UNIQUE NOT NULL,
    description     TEXT,
    embedding       BLOB,
    embedding_model TEXT,
    embedding_text  TEXT,
    embedded_at     DATETIME,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_usage_event_label ON usage_event(label_name, property_name);
CREATE INDEX IF NOT EXISTS idx_usage_event_session ON usage_event(session_id);
CREATE INDEX IF NOT EXISTS idx_property_ranking_label ON property_ranking(label_name);
CREATE INDEX IF NOT EXISTS idx_label_profile_embedding ON label_profile(embedding) WHERE embedding IS NOT NULL;
