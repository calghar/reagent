package resources

import "fmt"

func init() { Register(findingHandler{}) }

type findingHandler struct{}

func (findingHandler) Kind() string  { return KindFinding }
func (findingHandler) New() Resource { return &Finding{} }
func (findingHandler) ListColumns() []string {
	return []string{"NAME", "RULE", "SEVERITY", "FILE", "LINE"}
}
func (findingHandler) ToRow(r Resource) []string {
	f := r.(*Finding)
	return []string{f.Metadata.Name, f.Spec.RuleID, string(f.Spec.Severity), f.Spec.File, fmt.Sprintf("%d", f.Spec.Line)}
}
func (findingHandler) DescribeFields(r Resource) []Field {
	f := r.(*Finding)
	return []Field{
		{"Name", f.Metadata.Name},
		{"Rule ID", f.Spec.RuleID},
		{"Severity", string(f.Spec.Severity)},
		{"File", f.Spec.File},
		{"Line", fmt.Sprintf("%d", f.Spec.Line)},
		{"Description", f.Spec.Description},
		{"Content Hash", f.Spec.ContentHash},
	}
}

// Severity levels emitted by the scanner.
type Severity string

const (
	SeverityCritical Severity = "CRITICAL"
	SeverityHigh     Severity = "HIGH"
	SeverityMedium   Severity = "MEDIUM"
	SeverityLow      Severity = "LOW"
)

// Finding is a single scanner hit.
type Finding struct {
	TypeMeta `             yaml:",inline"`
	Metadata ObjectMeta  `json:"metadata" yaml:"metadata"`
	Spec     FindingSpec `json:"spec"     yaml:"spec"`
}

type FindingSpec struct {
	RuleID      string   `json:"ruleId"               yaml:"ruleId"`
	Severity    Severity `json:"severity"             yaml:"severity"`
	File        string   `json:"file"                 yaml:"file"`
	Line        int      `json:"line,omitempty"       yaml:"line,omitempty"`
	Description string   `json:"description"          yaml:"description"`
	AtlasIDs    []string `json:"atlasIds,omitempty"   yaml:"atlasIds,omitempty"`
	OWASPIDs    []string `json:"owaspIds,omitempty"   yaml:"owaspIds,omitempty"`
	ContentHash string   `json:"contentHash,omitempty" yaml:"contentHash,omitempty"`
}

func (f Finding) GetTypeMeta() TypeMeta   { return f.TypeMeta }
func (f Finding) GetMetadata() ObjectMeta { return f.Metadata }

func (f Finding) Validate() error {
	if err := validateTypeMeta(f.TypeMeta, KindFinding); err != nil {
		return err
	}
	if err := validateMetadata(f.Metadata); err != nil {
		return err
	}
	if f.Spec.RuleID == "" {
		return errSpec("ruleId")
	}
	switch f.Spec.Severity {
	case SeverityCritical, SeverityHigh, SeverityMedium, SeverityLow:
		return nil
	default:
		return errSpec("severity")
	}
}
