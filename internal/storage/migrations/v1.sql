-- v1: single resources table covers every kind. Body is the JSON-encoded
-- resource. Indexed columns are pulled out for filtering/joins; everything
-- else is recoverable from body.

CREATE TABLE IF NOT EXISTS resources (
    kind         TEXT NOT NULL,
    name         TEXT NOT NULL,
    content_hash TEXT,
    signed_at    TEXT,
    updated_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    body         BLOB NOT NULL,
    PRIMARY KEY (kind, name)
);

CREATE INDEX IF NOT EXISTS idx_resources_content_hash ON resources(content_hash);
CREATE INDEX IF NOT EXISTS idx_resources_kind ON resources(kind);
