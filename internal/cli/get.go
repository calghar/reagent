package cli

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/dynatrace-oss/dtguard/internal/auth"
	"github.com/dynatrace-oss/dtguard/internal/dt"
	"github.com/dynatrace-oss/dtguard/internal/output"
	"github.com/dynatrace-oss/dtguard/internal/resources"
	"github.com/spf13/cobra"
)

func newGetCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "get <kind> [name]",
		Short: "List or fetch resources by kind",
		Long:  "List all resources of a kind, or fetch a single resource by name.\nKinds: " + strings.Join(resources.Kinds(), ", "),
		Args:  cobra.RangeArgs(1, 2),
		RunE:  runGet,
	}
	cmd.Flags().Bool("local", false, "read from local cache instead of DT API")
	return cmd
}

func runGet(cmd *cobra.Command, args []string) error {
	kind := resolveKind(args[0])
	h, ok := resources.GetHandler(kind)
	if !ok {
		return fmt.Errorf("unknown kind %q; valid kinds: %s", args[0], strings.Join(resources.Kinds(), ", "))
	}

	local, _ := cmd.Flags().GetBool("local")
	if local {
		return fmt.Errorf("--local requires shield to be installed (not yet implemented)")
	}

	tenantURL, token, err := auth.Token()
	if err != nil {
		return err
	}
	client := dt.New(tenantURL, token)
	ctx := context.Background()

	if len(args) == 2 {
		return getOne(ctx, cmd, client, h, kind, args[1])
	}
	return getList(ctx, cmd, client, h, kind)
}

func getOne(ctx context.Context, cmd *cobra.Command, client *dt.Client, h resources.ResourceHandler, kind, name string) error {
	docs, err := client.List(ctx, docType(kind))
	if err != nil {
		return fmt.Errorf("list %s: %w", kind, err)
	}
	for _, doc := range docs {
		r, err := decodeDoc(kind, doc)
		if err != nil {
			continue
		}
		if r.GetMetadata().Name == name {
			return output.FromCmd(cmd).Print(r)
		}
	}
	return fmt.Errorf("%s %q not found", kind, name)
}

func getList(ctx context.Context, cmd *cobra.Command, client *dt.Client, h resources.ResourceHandler, kind string) error {
	docs, err := client.List(ctx, docType(kind))
	if err != nil {
		return fmt.Errorf("list %s: %w", kind, err)
	}
	var items []resources.Resource
	for _, doc := range docs {
		r, err := decodeDoc(kind, doc)
		if err != nil {
			continue
		}
		items = append(items, r)
	}
	if len(items) == 0 {
		cmd.Printf("No %s resources found.\n", strings.ToLower(kind))
		return nil
	}
	// Build table view
	rows := make([]map[string]string, 0, len(items))
	cols := h.ListColumns()
	for _, item := range items {
		row := h.ToRow(item)
		m := make(map[string]string, len(cols))
		for i, col := range cols {
			if i < len(row) {
				m[col] = row[i]
			}
		}
		rows = append(rows, m)
	}
	return output.FromCmd(cmd).PrintList(rows)
}

func decodeDoc(kind string, doc dt.Document) (resources.Resource, error) {
	r, err := resources.NewResource(kind)
	if err != nil {
		return nil, err
	}
	if err := json.Unmarshal(doc.Content, r); err != nil {
		return nil, err
	}
	return r, nil
}

// docType returns the DT document type string for a kind.
func docType(kind string) string {
	return "dtguard." + strings.ToLower(kind)
}

// resolveKind normalizes user-supplied kind to the canonical form.
func resolveKind(s string) string {
	lower := strings.ToLower(s)
	for _, k := range resources.Kinds() {
		if strings.ToLower(k) == lower || lower+"s" == strings.ToLower(k)+"s" {
			return k
		}
	}
	// Handle plurals: "attestations" -> "Attestation"
	if strings.HasSuffix(lower, "s") {
		trimmed := strings.TrimSuffix(lower, "s")
		for _, k := range resources.Kinds() {
			if strings.ToLower(k) == trimmed {
				return k
			}
		}
	}
	return s
}
