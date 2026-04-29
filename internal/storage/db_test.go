package storage

import (
	"context"
	"errors"
	"path/filepath"
	"testing"
	"time"

	"github.com/dynatrace-oss/dtguard/internal/resources"
)

func TestPutGetListByContentHash(t *testing.T) {
	db, err := Open(filepath.Join(t.TempDir(), "dtguard.db"))
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer db.Close()
	ctx := context.Background()

	att := &resources.Attestation{
		TypeMeta: resources.TypeMeta{APIVersion: resources.APIVersion, Kind: resources.KindAttestation},
		Metadata: resources.ObjectMeta{Name: "docs-helper"},
		Spec: resources.AttestationSpec{
			Subject: resources.Subject{ContentHash: "sha256:abc"},
			Signature: resources.Signature{
				Value: "ed25519:0x", KeyID: "k1",
				SignerKind: resources.SignerHuman, SignerID: "alice",
				SignedAt: time.Now().UTC(),
			},
		},
	}
	if err := db.Put(ctx, att); err != nil {
		t.Fatalf("Put: %v", err)
	}

	got, err := db.Get(ctx, resources.KindAttestation, "docs-helper")
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	if got.GetMetadata().Name != "docs-helper" {
		t.Errorf("name: got %q", got.GetMetadata().Name)
	}

	hits, err := db.ByContentHash(ctx, resources.KindAttestation, "sha256:abc")
	if err != nil {
		t.Fatalf("ByContentHash: %v", err)
	}
	if len(hits) != 1 {
		t.Errorf("ByContentHash: want 1, got %d", len(hits))
	}

	if err := db.Delete(ctx, resources.KindAttestation, "docs-helper"); err != nil {
		t.Fatalf("Delete: %v", err)
	}
	if _, err := db.Get(ctx, resources.KindAttestation, "docs-helper"); !errors.Is(err, ErrNotFound) {
		t.Errorf("Get after Delete: want ErrNotFound, got %v", err)
	}
}
