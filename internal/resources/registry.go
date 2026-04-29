package resources

import (
	"fmt"
	"sort"
)

// Field is a key-value pair rendered by describe commands.
type Field struct {
	Name  string
	Value string
}

// ResourceHandler defines per-kind metadata and factory for the CLI.
type ResourceHandler interface {
	Kind() string
	New() Resource
	ListColumns() []string
	ToRow(Resource) []string
	DescribeFields(Resource) []Field
}

var handlers = map[string]ResourceHandler{}

// Register adds a handler to the global registry. Panics on duplicate.
func Register(h ResourceHandler) {
	k := h.Kind()
	if _, dup := handlers[k]; dup {
		panic(fmt.Sprintf("resources: duplicate handler for kind %q", k))
	}
	handlers[k] = h
}

// GetHandler returns the handler for kind, or false if unregistered.
func GetHandler(kind string) (ResourceHandler, bool) {
	h, ok := handlers[kind]
	return h, ok
}

// Kinds returns sorted registered kind names.
func Kinds() []string {
	out := make([]string, 0, len(handlers))
	for k := range handlers {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

// NewResource creates a zero-value resource via the registered handler.
func NewResource(kind string) (Resource, error) {
	h, ok := handlers[kind]
	if !ok {
		return nil, fmt.Errorf("unknown kind: %q", kind)
	}
	return h.New(), nil
}

// short truncates a hash to 12 chars for table display.
func short(s string) string {
	if len(s) > 12 {
		return s[:12]
	}
	return s
}
