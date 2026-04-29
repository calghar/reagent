package resources

func init() { Register(attestationHandler{}) }

type attestationHandler struct{}

func (attestationHandler) Kind() string  { return KindAttestation }
func (attestationHandler) New() Resource { return &Attestation{} }
func (attestationHandler) ListColumns() []string {
	return []string{"NAME", "CONTENT-HASH", "SIGNER", "SIGNED-AT"}
}
func (attestationHandler) ToRow(r Resource) []string {
	a := r.(*Attestation)
	return []string{
		a.Metadata.Name,
		short(a.Spec.Subject.ContentHash),
		string(a.Spec.Signature.SignerKind) + ":" + a.Spec.Signature.SignerID,
		a.Spec.Signature.SignedAt.Format("2006-01-02T15:04:05Z"),
	}
}
func (attestationHandler) DescribeFields(r Resource) []Field {
	a := r.(*Attestation)
	return []Field{
		{"Name", a.Metadata.Name},
		{"Content Hash", a.Spec.Subject.ContentHash},
		{"Declaration Hash", a.Spec.Subject.DeclarationHash},
		{"Signer Kind", string(a.Spec.Signature.SignerKind)},
		{"Signer ID", a.Spec.Signature.SignerID},
		{"Key ID", a.Spec.Signature.KeyID},
		{"Signed At", a.Spec.Signature.SignedAt.Format("2006-01-02T15:04:05Z")},
		{"Provenance Ref", a.Spec.ProvenanceRef},
		{"Supersedes", a.Spec.Supersedes},
	}
}

// Attestation is a signed assertion that a content_hash's observed
// shape has been reviewed and approved as policy.
type Attestation struct {
	TypeMeta `                  yaml:",inline"`
	Metadata ObjectMeta      `json:"metadata" yaml:"metadata"`
	Spec     AttestationSpec `json:"spec"     yaml:"spec"`
}

// AttestationSpec is the body of an Attestation. Signature is excluded
// from the signing payload.
type AttestationSpec struct {
	Subject         Subject       `json:"subject"                   yaml:"subject"`
	ObservedShape   ObservedShape `json:"observedShape"             yaml:"observedShape"`
	ProvenanceRef   string        `json:"provenanceRef,omitempty"   yaml:"provenanceRef,omitempty"`
	Supersedes      string        `json:"supersedes,omitempty"      yaml:"supersedes,omitempty"`
	DavisProposalID string        `json:"davisProposalId,omitempty" yaml:"davisProposalId,omitempty"`
	Signature       Signature     `json:"signature"                 yaml:"signature"`
}

func (a Attestation) GetTypeMeta() TypeMeta   { return a.TypeMeta }
func (a Attestation) GetMetadata() ObjectMeta { return a.Metadata }

func (a Attestation) Validate() error {
	if err := validateTypeMeta(a.TypeMeta, KindAttestation); err != nil {
		return err
	}
	if err := validateMetadata(a.Metadata); err != nil {
		return err
	}
	if err := validateSubject(a.Spec.Subject); err != nil {
		return err
	}
	return validateSignature(a.Spec.Signature)
}
