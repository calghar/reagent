package resources

import "strings"

func init() { Register(floorHandler{}) }

type floorHandler struct{}

func (floorHandler) Kind() string  { return KindFloor }
func (floorHandler) New() Resource { return &Floor{} }
func (floorHandler) ListColumns() []string {
	return []string{"NAME", "BASH-PREFIXES", "WRITE-GLOBS", "EGRESS-HOSTS"}
}
func (floorHandler) ToRow(r Resource) []string {
	f := r.(*Floor)
	return []string{
		f.Metadata.Name,
		strings.Join(f.Spec.BashPrefixes, ", "),
		strings.Join(f.Spec.WriteGlobs, ", "),
		strings.Join(f.Spec.EgressHosts, ", "),
	}
}
func (floorHandler) DescribeFields(r Resource) []Field {
	f := r.(*Floor)
	return []Field{
		{"Name", f.Metadata.Name},
		{"Bash Prefixes", strings.Join(f.Spec.BashPrefixes, "\n  ")},
		{"Write Globs", strings.Join(f.Spec.WriteGlobs, "\n  ")},
		{"Egress Hosts", strings.Join(f.Spec.EgressHosts, "\n  ")},
	}
}

// Floor is the universal deny-list applied in every state. The bundled
// default ships embedded; users override via DTGUARD_UNIVERSAL_FLOOR.
type Floor struct {
	TypeMeta `           yaml:",inline"`
	Metadata ObjectMeta `json:"metadata" yaml:"metadata"`
	Spec     FloorSpec  `json:"spec"     yaml:"spec"`
}

type FloorSpec struct {
	BashPrefixes []string `json:"bashPrefixes,omitempty" yaml:"bashPrefixes,omitempty"`
	WriteGlobs   []string `json:"writeGlobs,omitempty"   yaml:"writeGlobs,omitempty"`
	EgressHosts  []string `json:"egressHosts,omitempty"  yaml:"egressHosts,omitempty"`
}

func (f Floor) GetTypeMeta() TypeMeta   { return f.TypeMeta }
func (f Floor) GetMetadata() ObjectMeta { return f.Metadata }

func (f Floor) Validate() error {
	if err := validateTypeMeta(f.TypeMeta, KindFloor); err != nil {
		return err
	}
	return validateMetadata(f.Metadata)
}
