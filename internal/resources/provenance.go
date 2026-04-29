package resources

func init() { Register(provenanceHandler{}) }

type provenanceHandler struct{}

func (provenanceHandler) Kind() string  { return KindProvenance }
func (provenanceHandler) New() Resource { return &Provenance{} }
func (provenanceHandler) ListColumns() []string {
	return []string{"NAME", "CONTENT-HASH", "COMMIT", "AUTHOR"}
}
func (provenanceHandler) ToRow(r Resource) []string {
	p := r.(*Provenance)
	return []string{p.Metadata.Name, short(p.Spec.Subject.ContentHash), short(p.Spec.Commit), p.Spec.Author}
}
func (provenanceHandler) DescribeFields(r Resource) []Field {
	p := r.(*Provenance)
	return []Field{
		{"Name", p.Metadata.Name},
		{"Content Hash", p.Spec.Subject.ContentHash},
		{"Commit", p.Spec.Commit},
		{"Repo", p.Spec.Repo},
		{"Branch", p.Spec.Branch},
		{"Author", p.Spec.Author},
		{"Timestamp", p.Spec.Timestamp},
	}
}

// Provenance records that a given content_hash was merged via a
// specific commit. One per merge.
type Provenance struct {
	TypeMeta `                yaml:",inline"`
	Metadata ObjectMeta     `json:"metadata" yaml:"metadata"`
	Spec     ProvenanceSpec `json:"spec"     yaml:"spec"`
}

type ProvenanceSpec struct {
	Subject   Subject `json:"subject"   yaml:"subject"`
	Commit    string  `json:"commit"    yaml:"commit"`
	Repo      string  `json:"repo"      yaml:"repo"`
	Branch    string  `json:"branch"    yaml:"branch"`
	Author    string  `json:"author"    yaml:"author"`
	Timestamp string  `json:"timestamp" yaml:"timestamp"`
}

func (p Provenance) GetTypeMeta() TypeMeta   { return p.TypeMeta }
func (p Provenance) GetMetadata() ObjectMeta { return p.Metadata }

func (p Provenance) Validate() error {
	if err := validateTypeMeta(p.TypeMeta, KindProvenance); err != nil {
		return err
	}
	if err := validateMetadata(p.Metadata); err != nil {
		return err
	}
	if err := validateSubject(p.Spec.Subject); err != nil {
		return err
	}
	if p.Spec.Commit == "" {
		return errSpec("commit")
	}
	return nil
}
