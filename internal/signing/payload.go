// Package signing produces the canonical bytes that get signed and
// verified for every signed kind.
//
// The signing payload is canonical_json(spec_without_signature):
// the spec block, with any "signature" key stripped at every depth,
// re-marshalled with sorted keys and no insignificant whitespace.
//
// This decouples signature verification from any reformatting the
// transport (DT Documents API, YAML on disk) may apply.
package signing

import (
	"bytes"
	"encoding/json"
	"fmt"
)

// CanonicalPayload returns the bytes to sign for a spec value.
// The input may be any Go value json-marshallable into an object.
func CanonicalPayload(spec any) ([]byte, error) {
	raw, err := json.Marshal(spec)
	if err != nil {
		return nil, fmt.Errorf("marshal spec: %w", err)
	}
	var generic any
	if err := json.Unmarshal(raw, &generic); err != nil {
		return nil, fmt.Errorf("unmarshal spec: %w", err)
	}
	stripped := stripSignature(generic)
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	if err := enc.Encode(stripped); err != nil {
		return nil, fmt.Errorf("encode canonical: %w", err)
	}
	// json.Encoder appends a newline; trim it.
	return bytes.TrimRight(buf.Bytes(), "\n"), nil
}

// stripSignature recursively removes "signature" keys from any map
// nested inside the value. Lists and scalars pass through.
func stripSignature(v any) any {
	switch t := v.(type) {
	case map[string]any:
		out := make(map[string]any, len(t))
		for k, val := range t {
			if k == "signature" {
				continue
			}
			out[k] = stripSignature(val)
		}
		return out
	case []any:
		out := make([]any, len(t))
		for i, val := range t {
			out[i] = stripSignature(val)
		}
		return out
	default:
		return v
	}
}
