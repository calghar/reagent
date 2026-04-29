package resources

import "fmt"

func init() { Register(assetHandler{}) }

type assetHandler struct{}

func (assetHandler) Kind() string  { return KindAsset }
func (assetHandler) New() Resource { return &Asset{} }
func (assetHandler) ListColumns() []string {
	return []string{"NAME", "PATH", "CONTENT-HASH", "STATE"}
}
func (assetHandler) ToRow(r Resource) []string {
	a := r.(*Asset)
	state := a.Spec.State
	if state == "" {
		state = StateObserved
	}
	return []string{a.Metadata.Name, a.Spec.Path, short(a.Spec.ContentHash), state}
}
func (assetHandler) DescribeFields(r Resource) []Field {
	a := r.(*Asset)
	state := a.Spec.State
	if state == "" {
		state = StateObserved
	}
	return []Field{
		{"Name", a.Metadata.Name},
		{"Path", a.Spec.Path},
		{"Content Hash", a.Spec.ContentHash},
		{"State", state},
		{"Size", fmt.Sprintf("%d", a.Spec.Size)},
		{"Content Type", a.Spec.ContentType},
	}
}

// Asset is the local view of an AI-agent configuration file. Its
// content_hash is the join key for every other kind.
type Asset struct {
	TypeMeta `           yaml:",inline"`
	Metadata ObjectMeta `json:"metadata" yaml:"metadata"`
	Spec     AssetSpec  `json:"spec"     yaml:"spec"`
}

type AssetSpec struct {
	Path        string `json:"path"                  yaml:"path"`
	ContentHash string `json:"contentHash"           yaml:"contentHash"`
	State       string `json:"state,omitempty"       yaml:"state,omitempty"`
	Size        int64  `json:"size,omitempty"        yaml:"size,omitempty"`
	ContentType string `json:"contentType,omitempty" yaml:"contentType,omitempty"`
}

// Asset states.
const (
	StateObserved = "OBSERVED"
	StateAttested = "ATTESTED"
	StateRevoked  = "REVOKED"
)

func (a Asset) GetTypeMeta() TypeMeta   { return a.TypeMeta }
func (a Asset) GetMetadata() ObjectMeta { return a.Metadata }

func (a Asset) Validate() error {
	if err := validateTypeMeta(a.TypeMeta, KindAsset); err != nil {
		return err
	}
	if err := validateMetadata(a.Metadata); err != nil {
		return err
	}
	if a.Spec.ContentHash == "" {
		return errSpec("contentHash")
	}
	if a.Spec.Path == "" {
		return errSpec("path")
	}
	switch a.Spec.State {
	case "", StateObserved, StateAttested, StateRevoked:
		return nil
	default:
		return errSpec("state")
	}
}
