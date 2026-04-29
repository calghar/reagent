package resources

import (
	"testing"
)

func TestRegistryAllKindsRegistered(t *testing.T) {
	want := []string{
		KindAsset, KindAttestation, KindFinding, KindFloor,
		KindProposal, KindProvenance, KindRevocation,
	}
	got := Kinds()
	if len(got) != len(want) {
		t.Fatalf("Kinds() = %v, want %v", got, want)
	}
	for i, k := range want {
		if got[i] != k {
			t.Errorf("Kinds()[%d] = %q, want %q", i, got[i], k)
		}
	}
}

func TestGetHandlerKnown(t *testing.T) {
	for _, kind := range Kinds() {
		t.Run(kind, func(t *testing.T) {
			h, ok := GetHandler(kind)
			if !ok {
				t.Fatalf("GetHandler(%q) = false", kind)
			}
			if h.Kind() != kind {
				t.Errorf("handler.Kind() = %q, want %q", h.Kind(), kind)
			}
			r := h.New()
			if r == nil {
				t.Fatal("handler.New() = nil")
			}
			cols := h.ListColumns()
			if len(cols) == 0 {
				t.Error("handler.ListColumns() empty")
			}
		})
	}
}

func TestGetHandlerUnknown(t *testing.T) {
	_, ok := GetHandler("Bogus")
	if ok {
		t.Error("GetHandler(\"Bogus\") = true, want false")
	}
}

func TestNewResourceUnknown(t *testing.T) {
	_, err := NewResource("Bogus")
	if err == nil {
		t.Error("NewResource(\"Bogus\") = nil error, want error")
	}
}

func TestHandlerToRow(t *testing.T) {
	h, _ := GetHandler(KindAsset)
	a := &Asset{
		TypeMeta: TypeMeta{APIVersion: APIVersion, Kind: KindAsset},
		Metadata: ObjectMeta{Name: "test-asset"},
		Spec: AssetSpec{
			Path:        ".claude/skills/test/SKILL.md",
			ContentHash: "abcdef123456789012345678",
			State:       StateAttested,
		},
	}
	row := h.ToRow(a)
	if row[0] != "test-asset" {
		t.Errorf("row[0] = %q, want %q", row[0], "test-asset")
	}
	if row[2] != "abcdef123456" {
		t.Errorf("row[2] = %q, want 12-char truncation", row[2])
	}
	if row[3] != StateAttested {
		t.Errorf("row[3] = %q, want %q", row[3], StateAttested)
	}
}

func TestHandlerDescribeFields(t *testing.T) {
	h, _ := GetHandler(KindAsset)
	a := &Asset{
		TypeMeta: TypeMeta{APIVersion: APIVersion, Kind: KindAsset},
		Metadata: ObjectMeta{Name: "my-asset"},
		Spec: AssetSpec{
			Path:        "path/to/file",
			ContentHash: "hash123",
			State:       StateObserved,
		},
	}
	fields := h.DescribeFields(a)
	if len(fields) == 0 {
		t.Fatal("DescribeFields returned empty")
	}
	if fields[0].Value != "my-asset" {
		t.Errorf("fields[0].Value = %q, want %q", fields[0].Value, "my-asset")
	}
}
