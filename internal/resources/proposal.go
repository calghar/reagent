package resources

import "fmt"

func init() { Register(proposalHandler{}) }

type proposalHandler struct{}

func (proposalHandler) Kind() string  { return KindProposal }
func (proposalHandler) New() Resource { return &Proposal{} }
func (proposalHandler) ListColumns() []string {
	return []string{"NAME", "CONTENT-HASH", "WINDOW", "CALLS"}
}
func (proposalHandler) ToRow(r Resource) []string {
	p := r.(*Proposal)
	window := p.Spec.Window.From + " → " + p.Spec.Window.To
	return []string{p.Metadata.Name, short(p.Spec.Subject.ContentHash), window, fmt.Sprintf("%d", p.Spec.CallCount)}
}
func (proposalHandler) DescribeFields(r Resource) []Field {
	p := r.(*Proposal)
	return []Field{
		{"Name", p.Metadata.Name},
		{"Content Hash", p.Spec.Subject.ContentHash},
		{"Window From", p.Spec.Window.From},
		{"Window To", p.Spec.Window.To},
		{"Call Count", fmt.Sprintf("%d", p.Spec.CallCount)},
		{"Provenance Ref", p.Spec.ProvenanceRef},
		{"Supersedes", p.Spec.Supersedes},
	}
}

// Proposal is an unsigned candidate Attestation produced by Davis once
// an asset's shape stabilizes. Signing it produces an Attestation.
type Proposal struct {
	TypeMeta `              yaml:",inline"`
	Metadata ObjectMeta   `json:"metadata" yaml:"metadata"`
	Spec     ProposalSpec `json:"spec"     yaml:"spec"`
}

// ProposalSpec is an Attestation body without the signature.
type ProposalSpec struct {
	Subject       Subject       `json:"subject"                 yaml:"subject"`
	ObservedShape ObservedShape `json:"observedShape"           yaml:"observedShape"`
	ProvenanceRef string        `json:"provenanceRef,omitempty" yaml:"provenanceRef,omitempty"`
	Supersedes    string        `json:"supersedes,omitempty"    yaml:"supersedes,omitempty"`
	Window        Window        `json:"window"                  yaml:"window"`
	CallCount     int           `json:"callCount"               yaml:"callCount"`
}

// Window is the observation window the proposal was computed over.
type Window struct {
	From string `json:"from" yaml:"from"`
	To   string `json:"to"   yaml:"to"`
}

func (p Proposal) GetTypeMeta() TypeMeta   { return p.TypeMeta }
func (p Proposal) GetMetadata() ObjectMeta { return p.Metadata }

func (p Proposal) Validate() error {
	if err := validateTypeMeta(p.TypeMeta, KindProposal); err != nil {
		return err
	}
	if err := validateMetadata(p.Metadata); err != nil {
		return err
	}
	return validateSubject(p.Spec.Subject)
}
