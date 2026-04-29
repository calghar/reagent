// Package resources defines the dtguard resource model.
//
// Every kind shares the apiVersion/kind/metadata/spec envelope. Crypto
// fields live under spec, never metadata. Signing payload is
// canonical_json(spec_without_signature) — see internal/signing/payload.
package resources

import (
	"errors"
	"fmt"
	"time"
)

// APIVersion is the only apiVersion dtguard resources carry in v1.
const APIVersion = "dtguard.io/v1"

// Kinds.
const (
	KindAsset       = "Asset"
	KindAttestation = "Attestation"
	KindProposal    = "Proposal"
	KindProvenance  = "Provenance"
	KindRevocation  = "Revocation"
	KindFinding     = "Finding"
	KindFloor       = "Floor"
)

// TypeMeta is the apiVersion+kind preamble every resource carries.
type TypeMeta struct {
	APIVersion string `json:"apiVersion" yaml:"apiVersion"`
	Kind       string `json:"kind"       yaml:"kind"`
}

// ObjectMeta is the metadata block. Crypto fields never live here.
type ObjectMeta struct {
	Name        string            `json:"name"                  yaml:"name"`
	Labels      map[string]string `json:"labels,omitempty"      yaml:"labels,omitempty"`
	Annotations map[string]string `json:"annotations,omitempty" yaml:"annotations,omitempty"`
	CreatedAt   *time.Time        `json:"createdAt,omitempty"   yaml:"createdAt,omitempty"`
}

// Subject identifies the asset bytes a record pertains to.
type Subject struct {
	ContentHash     string `json:"contentHash"               yaml:"contentHash"`
	DeclarationHash string `json:"declarationHash,omitempty" yaml:"declarationHash,omitempty"`
}

// ObservedShape is the four-dimension behavioral fingerprint.
type ObservedShape struct {
	Tools         []string `json:"tools,omitempty"         yaml:"tools,omitempty"`
	EgressHosts   []string `json:"egressHosts,omitempty"   yaml:"egressHosts,omitempty"`
	BashPrefixes  []string `json:"bashPrefixes,omitempty"  yaml:"bashPrefixes,omitempty"`
	WriteGlobs    []string `json:"writeGlobs,omitempty"    yaml:"writeGlobs,omitempty"`
}

// SignerKind discriminates how an Attestation came to exist. The trust
// anchor is the public key registered for SignerID, not the kind.
type SignerKind string

const (
	SignerHuman  SignerKind = "human"
	SignerDavis  SignerKind = "davis"
	SignerPolicy SignerKind = "policy"
)

// Signature is embedded in spec for signed kinds. Excluded from the
// signing payload (see internal/signing).
type Signature struct {
	Value      string     `json:"value"      yaml:"value"`
	KeyID      string     `json:"keyId"      yaml:"keyId"`
	SignerKind SignerKind `json:"signerKind" yaml:"signerKind"`
	SignerID   string     `json:"signerId"   yaml:"signerId"`
	SignedAt   time.Time  `json:"signedAt"   yaml:"signedAt"`
}

// Resource is the common interface every kind implements.
type Resource interface {
	GetTypeMeta() TypeMeta
	GetMetadata() ObjectMeta
	Validate() error
}

// validateTypeMeta checks the envelope shared by every kind.
func validateTypeMeta(tm TypeMeta, wantKind string) error {
	if tm.APIVersion != APIVersion {
		return fmt.Errorf("apiVersion: want %q, got %q", APIVersion, tm.APIVersion)
	}
	if tm.Kind != wantKind {
		return fmt.Errorf("kind: want %q, got %q", wantKind, tm.Kind)
	}
	return nil
}

// validateMetadata enforces the rules common to every kind's metadata.
func validateMetadata(m ObjectMeta) error {
	if m.Name == "" {
		return errors.New("metadata.name: required")
	}
	return nil
}

// validateSubject enforces the rules common to every Subject block.
func validateSubject(s Subject) error {
	if s.ContentHash == "" {
		return errors.New("spec.subject.contentHash: required")
	}
	return nil
}

// errSpec returns "spec.<field>: required" for trivial required-field errors.
func errSpec(field string) error {
	return fmt.Errorf("spec.%s: required", field)
}

// validateSignature enforces the rules common to every Signature block.
func validateSignature(s Signature) error {
	switch {
	case s.Value == "":
		return errors.New("spec.signature.value: required")
	case s.KeyID == "":
		return errors.New("spec.signature.keyId: required")
	case s.SignerID == "":
		return errors.New("spec.signature.signerId: required")
	case s.SignedAt.IsZero():
		return errors.New("spec.signature.signedAt: required")
	}
	switch s.SignerKind {
	case SignerHuman, SignerDavis, SignerPolicy:
		return nil
	default:
		return fmt.Errorf("spec.signature.signerKind: want one of human|davis|policy, got %q", s.SignerKind)
	}
}
