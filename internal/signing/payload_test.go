package signing

import (
	"testing"
)

func TestCanonicalPayload_StripsSignatureAndSortsKeys(t *testing.T) {
	a := map[string]any{
		"zeta":      1,
		"alpha":     2,
		"signature": map[string]any{"value": "must-be-stripped"},
		"nested": map[string]any{
			"signature": "also-stripped",
			"keep":      []any{map[string]any{"signature": "deep", "ok": true}},
		},
	}
	b := map[string]any{
		"alpha":     2,
		"zeta":      1,
		"signature": map[string]any{"value": "different-but-stripped"},
		"nested": map[string]any{
			"keep": []any{map[string]any{"ok": true}},
		},
	}

	pa, err := CanonicalPayload(a)
	if err != nil {
		t.Fatalf("CanonicalPayload(a): %v", err)
	}
	pb, err := CanonicalPayload(b)
	if err != nil {
		t.Fatalf("CanonicalPayload(b): %v", err)
	}
	if string(pa) != string(pb) {
		t.Errorf("payloads differ:\n a=%s\n b=%s", pa, pb)
	}
	want := `{"alpha":2,"nested":{"keep":[{"ok":true}]},"zeta":1}`
	if string(pa) != want {
		t.Errorf("canonical form:\n want=%s\n  got=%s", want, pa)
	}
}
