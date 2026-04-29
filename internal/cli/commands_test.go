package cli

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/dynatrace-oss/dtguard/internal/dt"
	"github.com/dynatrace-oss/dtguard/internal/resources"
)

func TestResolveKind(t *testing.T) {
	tests := []struct {
		in   string
		want string
	}{
		{"asset", resources.KindAsset},
		{"Asset", resources.KindAsset},
		{"attestations", resources.KindAttestation},
		{"finding", resources.KindFinding},
		{"floors", resources.KindFloor},
		{"Bogus", "Bogus"},
	}
	for _, tt := range tests {
		t.Run(tt.in, func(t *testing.T) {
			got := resolveKind(tt.in)
			if got != tt.want {
				t.Errorf("resolveKind(%q) = %q, want %q", tt.in, got, tt.want)
			}
		})
	}
}

func TestDocType(t *testing.T) {
	if got := docType(resources.KindAttestation); got != "dtguard.attestation" {
		t.Errorf("docType(Attestation) = %q", got)
	}
}

func TestApplyDryRun(t *testing.T) {
	dir := t.TempDir()
	file := filepath.Join(dir, "asset.yaml")
	content := `apiVersion: dtguard.io/v1
kind: Asset
metadata:
  name: test
spec:
  path: foo/bar.md
  contentHash: abc123
`
	if err := os.WriteFile(file, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}

	var buf bytes.Buffer
	root := NewRootCmd()
	root.SetOut(&buf)
	root.SetErr(&buf)
	root.SetArgs([]string{"apply", "-f", file, "--dry-run"})
	if err := root.Execute(); err != nil {
		t.Fatalf("apply --dry-run failed: %v", err)
	}
	if !strings.Contains(buf.String(), "validated successfully") {
		t.Errorf("unexpected output: %q", buf.String())
	}
}

func TestGetUnknownKind(t *testing.T) {
	var buf bytes.Buffer
	root := NewRootCmd()
	root.SetOut(&buf)
	root.SetErr(&buf)
	root.SetArgs([]string{"get", "boguskind"})
	err := root.Execute()
	if err == nil {
		t.Fatal("expected error for unknown kind")
	}
}

// testDTServer returns an httptest server that serves document list responses.
func testDTServer(t *testing.T, docs []dt.Document) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		resp := struct {
			Documents []dt.Document `json:"documents"`
		}{Documents: docs}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(resp)
	}))
}
