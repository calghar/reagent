package resources

import (
	"fmt"

	"gopkg.in/yaml.v3"
)

// DecodeYAML inspects the apiVersion/kind preamble and decodes into the
// matching concrete type. Returns the resource and its kind.
func DecodeYAML(data []byte) (Resource, error) {
	var head TypeMeta
	if err := yaml.Unmarshal(data, &head); err != nil {
		return nil, fmt.Errorf("decode preamble: %w", err)
	}
	if head.APIVersion != APIVersion {
		return nil, fmt.Errorf("apiVersion: want %q, got %q", APIVersion, head.APIVersion)
	}

	r, err := NewResource(head.Kind)
	if err != nil {
		return nil, err
	}
	if err := yaml.Unmarshal(data, r); err != nil {
		return nil, fmt.Errorf("decode %s: %w", head.Kind, err)
	}
	if err := r.Validate(); err != nil {
		return nil, fmt.Errorf("validate %s: %w", head.Kind, err)
	}
	return r, nil
}
