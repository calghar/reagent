package resources

func init() { Register(revocationHandler{}) }

type revocationHandler struct{}

func (revocationHandler) Kind() string  { return KindRevocation }
func (revocationHandler) New() Resource { return &Revocation{} }
func (revocationHandler) ListColumns() []string {
	return []string{"NAME", "CONTENT-HASH", "REASON", "SIGNED-AT"}
}
func (revocationHandler) ToRow(r Resource) []string {
	rv := r.(*Revocation)
	return []string{
		rv.Metadata.Name,
		short(rv.Spec.Subject.ContentHash),
		rv.Spec.Reason,
		rv.Spec.Signature.SignedAt.Format("2006-01-02T15:04:05Z"),
	}
}
func (revocationHandler) DescribeFields(r Resource) []Field {
	rv := r.(*Revocation)
	return []Field{
		{"Name", rv.Metadata.Name},
		{"Content Hash", rv.Spec.Subject.ContentHash},
		{"Reason", rv.Spec.Reason},
		{"Signer Kind", string(rv.Spec.Signature.SignerKind)},
		{"Signer ID", rv.Spec.Signature.SignerID},
		{"Signed At", rv.Spec.Signature.SignedAt.Format("2006-01-02T15:04:05Z")},
	}
}

// Revocation marks a content_hash as untrusted. Append-only — never
// mutates the underlying Attestation.
type Revocation struct {
	TypeMeta `                yaml:",inline"`
	Metadata ObjectMeta     `json:"metadata" yaml:"metadata"`
	Spec     RevocationSpec `json:"spec"     yaml:"spec"`
}

type RevocationSpec struct {
	Subject   Subject   `json:"subject"   yaml:"subject"`
	Reason    string    `json:"reason"    yaml:"reason"`
	Signature Signature `json:"signature" yaml:"signature"`
}

func (r Revocation) GetTypeMeta() TypeMeta   { return r.TypeMeta }
func (r Revocation) GetMetadata() ObjectMeta { return r.Metadata }

func (r Revocation) Validate() error {
	if err := validateTypeMeta(r.TypeMeta, KindRevocation); err != nil {
		return err
	}
	if err := validateMetadata(r.Metadata); err != nil {
		return err
	}
	if err := validateSubject(r.Spec.Subject); err != nil {
		return err
	}
	if r.Spec.Reason == "" {
		return errSpec("reason")
	}
	return validateSignature(r.Spec.Signature)
}
