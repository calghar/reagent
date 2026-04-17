-- AgentGuard SQLite schema (migration v1)
-- All structured data for the agentguard CLI tool.

-- Workflow / repo profiles
CREATE TABLE IF NOT EXISTS profiles (
    profile_id   TEXT PRIMARY KEY,
    repo_path    TEXT NOT NULL UNIQUE,
    repo_name    TEXT NOT NULL,
    data_json    TEXT NOT NULL,  -- serialised RepoProfile
    updated_at   TEXT NOT NULL
);

-- Learned instincts / patterns
CREATE TABLE IF NOT EXISTS instincts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    instinct_id     TEXT NOT NULL UNIQUE,
    content         TEXT NOT NULL,
    category        TEXT NOT NULL,
    trust_tier      TEXT NOT NULL DEFAULT 'workspace',
    confidence      REAL NOT NULL DEFAULT 0.5,
    source          TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    last_used       TEXT,
    use_count       INTEGER NOT NULL DEFAULT 0,
    success_rate    REAL NOT NULL DEFAULT 0.0,
    ttl_days        INTEGER NOT NULL DEFAULT 90
);

-- LLM cost entries
CREATE TABLE IF NOT EXISTS cost_entries (
    cost_id        TEXT PRIMARY KEY,
    timestamp      TEXT NOT NULL,
    provider       TEXT NOT NULL,
    model          TEXT NOT NULL,
    asset_type     TEXT NOT NULL DEFAULT '',
    asset_name     TEXT NOT NULL DEFAULT '',
    input_tokens   INTEGER NOT NULL,
    output_tokens  INTEGER NOT NULL,
    cost_usd       REAL NOT NULL,
    latency_ms     INTEGER NOT NULL,
    tier           TEXT NOT NULL DEFAULT 'standard',
    was_fallback   INTEGER NOT NULL DEFAULT 0
);

-- Asset evaluation history
CREATE TABLE IF NOT EXISTS evaluations (
    evaluation_id  TEXT PRIMARY KEY,
    asset_path     TEXT NOT NULL,
    asset_type     TEXT NOT NULL,
    asset_name     TEXT NOT NULL,
    quality_score  REAL NOT NULL,
    invocation_rate REAL,
    correction_rate REAL,
    issues_json    TEXT NOT NULL DEFAULT '[]',
    evaluated_at   TEXT NOT NULL,
    repo_path      TEXT NOT NULL
);

-- Generation cache (content-hash keyed)
CREATE TABLE IF NOT EXISTS generations (
    cache_key      TEXT PRIMARY KEY,
    asset_type     TEXT NOT NULL,
    name           TEXT NOT NULL,
    content        TEXT NOT NULL,
    generated_at   TEXT NOT NULL,
    provider       TEXT NOT NULL,
    model          TEXT NOT NULL,
    cost_usd       REAL NOT NULL DEFAULT 0.0,
    profile_hash   TEXT NOT NULL,
    instinct_hash  TEXT NOT NULL DEFAULT ''
);

-- Autonomous loop run records (migration v2)
CREATE TABLE IF NOT EXISTS loops (
    loop_id      TEXT PRIMARY KEY,
    loop_type    TEXT NOT NULL,
    repo_path    TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'running',
    stop_reason  TEXT,
    iteration    INTEGER NOT NULL DEFAULT 0,
    total_cost   REAL NOT NULL DEFAULT 0.0,
    avg_score    REAL,
    started_at   TEXT NOT NULL,
    completed_at TEXT
);

-- Assets awaiting human approval before deployment (migration v2)
CREATE TABLE IF NOT EXISTS pending_assets (
    pending_id        TEXT PRIMARY KEY,
    asset_type        TEXT NOT NULL,
    asset_name        TEXT NOT NULL,
    file_path         TEXT NOT NULL,
    content           TEXT NOT NULL,
    previous_content  TEXT,
    previous_score    REAL,
    new_score         REAL NOT NULL,
    generation_method TEXT NOT NULL,
    loop_id           TEXT NOT NULL,
    iteration         INTEGER NOT NULL,
    created_at        TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'pending'
);

-- FTS5 full-text index over instincts
CREATE VIRTUAL TABLE IF NOT EXISTS instincts_fts USING fts5(
    content,
    category,
    source,
    content='instincts',
    content_rowid='id'
);

-- Triggers to keep FTS in sync with instincts table
CREATE TRIGGER IF NOT EXISTS instincts_ai AFTER INSERT ON instincts BEGIN
    INSERT INTO instincts_fts(rowid, content, category, source)
    VALUES (new.id, new.content, new.category, new.source);
END;

CREATE TRIGGER IF NOT EXISTS instincts_ad AFTER DELETE ON instincts BEGIN
    INSERT INTO instincts_fts(instincts_fts, rowid, content, category, source)
    VALUES ('delete', old.id, old.content, old.category, old.source);
END;

CREATE TRIGGER IF NOT EXISTS instincts_au AFTER UPDATE ON instincts BEGIN
    INSERT INTO instincts_fts(instincts_fts, rowid, content, category, source)
    VALUES ('delete', old.id, old.content, old.category, old.source);
    INSERT INTO instincts_fts(rowid, content, category, source)
    VALUES (new.id, new.content, new.category, new.source);
END;
