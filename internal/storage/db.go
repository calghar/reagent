// Package storage is the local SQLite cache used by the opt-in shield.
// It exists ONLY when `dtguard shield install` has been run; observe
// mode never opens a database.
//
// One unified `resources` table holds every kind. Bodies are stored as
// canonical JSON; indexed columns (content_hash, signed_at) are pulled
// out for filtering. Schema is single-version: see migrations/v1.sql.
package storage

import (
	"context"
	"database/sql"
	_ "embed"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"time"

	_ "modernc.org/sqlite"

	"github.com/dynatrace-oss/dtguard/internal/resources"
)

//go:embed migrations/v1.sql
var schemaV1 string

// ErrNotFound is returned by Get when no row matches.
var ErrNotFound = errors.New("not found")

// DB is the local cache handle.
type DB struct {
	sql *sql.DB
}

// Open opens (and migrates if needed) the SQLite database at path.
// Parent directories are created with mode 0700.
func Open(path string) (*DB, error) {
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return nil, fmt.Errorf("mkdir %s: %w", filepath.Dir(path), err)
	}
	conn, err := sql.Open("sqlite", path+"?_pragma=journal_mode(WAL)&_pragma=foreign_keys(on)")
	if err != nil {
		return nil, fmt.Errorf("open %s: %w", path, err)
	}
	if _, err := conn.Exec(schemaV1); err != nil {
		_ = conn.Close()
		return nil, fmt.Errorf("apply v1 schema: %w", err)
	}
	return &DB{sql: conn}, nil
}

// Close releases the underlying connection.
func (d *DB) Close() error { return d.sql.Close() }

// Put inserts or replaces a resource keyed by (kind, name).
func (d *DB) Put(ctx context.Context, r resources.Resource) error {
	body, err := json.Marshal(r)
	if err != nil {
		return fmt.Errorf("marshal: %w", err)
	}
	contentHash, signedAt := indexed(r)
	_, err = d.sql.ExecContext(ctx, `
		INSERT INTO resources (kind, name, content_hash, signed_at, body)
		VALUES (?, ?, ?, ?, ?)
		ON CONFLICT(kind, name) DO UPDATE SET
			content_hash = excluded.content_hash,
			signed_at    = excluded.signed_at,
			body         = excluded.body,
			updated_at   = strftime('%Y-%m-%dT%H:%M:%fZ','now')`,
		r.GetTypeMeta().Kind, r.GetMetadata().Name, contentHash, signedAt, body)
	if err != nil {
		return fmt.Errorf("put %s/%s: %w", r.GetTypeMeta().Kind, r.GetMetadata().Name, err)
	}
	return nil
}

// Get fetches a single resource by (kind, name). Returns ErrNotFound
// when no row matches.
func (d *DB) Get(ctx context.Context, kind, name string) (resources.Resource, error) {
	row := d.sql.QueryRowContext(ctx, `SELECT body FROM resources WHERE kind = ? AND name = ?`, kind, name)
	var body []byte
	if err := row.Scan(&body); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, ErrNotFound
		}
		return nil, fmt.Errorf("get %s/%s: %w", kind, name, err)
	}
	return decode(kind, body)
}

// List returns all resources of a kind.
func (d *DB) List(ctx context.Context, kind string) ([]resources.Resource, error) {
	rows, err := d.sql.QueryContext(ctx, `SELECT body FROM resources WHERE kind = ? ORDER BY name`, kind)
	if err != nil {
		return nil, fmt.Errorf("list %s: %w", kind, err)
	}
	defer rows.Close()
	return scanAll(kind, rows)
}

// ByContentHash returns every resource of kind whose content_hash matches.
// Used by the shield to look up the active record for an asset.
func (d *DB) ByContentHash(ctx context.Context, kind, hash string) ([]resources.Resource, error) {
	rows, err := d.sql.QueryContext(ctx, `
		SELECT body FROM resources
		WHERE kind = ? AND content_hash = ?
		ORDER BY signed_at DESC NULLS LAST, name`, kind, hash)
	if err != nil {
		return nil, fmt.Errorf("by content hash %s/%s: %w", kind, hash, err)
	}
	defer rows.Close()
	return scanAll(kind, rows)
}

// Delete removes a single resource. Missing rows are not an error.
func (d *DB) Delete(ctx context.Context, kind, name string) error {
	_, err := d.sql.ExecContext(ctx, `DELETE FROM resources WHERE kind = ? AND name = ?`, kind, name)
	if err != nil {
		return fmt.Errorf("delete %s/%s: %w", kind, name, err)
	}
	return nil
}

// indexed pulls the (content_hash, signed_at) columns out of a resource.
// Empty strings are stored as NULL; we use sql.NullString implicitly via
// passing nil when zero.
func indexed(r resources.Resource) (any, any) {
	var contentHash, signedAt any
	switch t := r.(type) {
	case *resources.Attestation:
		contentHash = nullable(t.Spec.Subject.ContentHash)
		signedAt = nullableTime(t.Spec.Signature.SignedAt)
	case *resources.Proposal:
		contentHash = nullable(t.Spec.Subject.ContentHash)
	case *resources.Provenance:
		contentHash = nullable(t.Spec.Subject.ContentHash)
	case *resources.Revocation:
		contentHash = nullable(t.Spec.Subject.ContentHash)
		signedAt = nullableTime(t.Spec.Signature.SignedAt)
	case *resources.Finding:
		contentHash = nullable(t.Spec.ContentHash)
	case *resources.Asset:
		contentHash = nullable(t.Spec.ContentHash)
	}
	return contentHash, signedAt
}

func nullable(s string) any {
	if s == "" {
		return nil
	}
	return s
}

func nullableTime(t time.Time) any {
	if t.IsZero() {
		return nil
	}
	return t.UTC().Format(time.RFC3339Nano)
}

func decode(kind string, body []byte) (resources.Resource, error) {
	var r resources.Resource
	switch kind {
	case resources.KindAsset:
		r = &resources.Asset{}
	case resources.KindAttestation:
		r = &resources.Attestation{}
	case resources.KindProposal:
		r = &resources.Proposal{}
	case resources.KindProvenance:
		r = &resources.Provenance{}
	case resources.KindRevocation:
		r = &resources.Revocation{}
	case resources.KindFinding:
		r = &resources.Finding{}
	case resources.KindFloor:
		r = &resources.Floor{}
	default:
		return nil, fmt.Errorf("unknown kind in db: %q", kind)
	}
	if err := json.Unmarshal(body, r); err != nil {
		return nil, fmt.Errorf("unmarshal %s: %w", kind, err)
	}
	return r, nil
}

func scanAll(kind string, rows *sql.Rows) ([]resources.Resource, error) {
	var out []resources.Resource
	for rows.Next() {
		var body []byte
		if err := rows.Scan(&body); err != nil {
			return nil, fmt.Errorf("scan %s: %w", kind, err)
		}
		r, err := decode(kind, body)
		if err != nil {
			return nil, err
		}
		out = append(out, r)
	}
	return out, rows.Err()
}

