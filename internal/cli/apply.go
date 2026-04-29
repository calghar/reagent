package cli

import (
	"context"
	"encoding/json"
	"fmt"
	"os"

	"github.com/dynatrace-oss/dtguard/internal/auth"
	"github.com/dynatrace-oss/dtguard/internal/dt"
	"github.com/dynatrace-oss/dtguard/internal/resources"
	"github.com/dynatrace-oss/dtguard/internal/safety"
	"github.com/spf13/cobra"
)

func newApplyCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "apply -f <file>",
		Short: "Create or update a resource from a YAML file",
		RunE:  runApply,
	}
	cmd.Flags().StringP("file", "f", "", "path to the resource YAML file (required)")
	_ = cmd.MarkFlagRequired("file")
	cmd.Flags().Bool("dry-run", false, "validate only, do not write")
	return cmd
}

func runApply(cmd *cobra.Command, _ []string) error {
	file, _ := cmd.Flags().GetString("file")
	dryRun, _ := cmd.Flags().GetBool("dry-run")

	data, err := os.ReadFile(file)
	if err != nil {
		return fmt.Errorf("read %s: %w", file, err)
	}

	r, err := resources.DecodeYAML(data)
	if err != nil {
		return fmt.Errorf("decode %s: %w", file, err)
	}

	if dryRun {
		cmd.Printf("%s/%s validated successfully (dry-run)\n", r.GetTypeMeta().Kind, r.GetMetadata().Name)
		return nil
	}

	if err := safety.Check(safety.OpCreate); err != nil {
		return err
	}

	tenantURL, token, err := auth.Token()
	if err != nil {
		return err
	}
	client := dt.New(tenantURL, token)
	ctx := context.Background()

	kind := r.GetTypeMeta().Kind
	name := r.GetMetadata().Name

	content, err := json.Marshal(r)
	if err != nil {
		return fmt.Errorf("marshal: %w", err)
	}

	doc := &dt.Document{
		Name:    fmt.Sprintf("%s/%s", kind, name),
		Type:    docType(kind),
		Content: content,
	}

	// Check if document exists (for upsert)
	existing, _ := findDoc(ctx, client, kind, name)
	if existing != nil {
		doc.ID = existing.ID
	}

	result, err := client.Apply(ctx, doc)
	if err != nil {
		return fmt.Errorf("apply %s/%s: %w", kind, name, err)
	}
	cmd.Printf("%s/%s applied (id=%s)\n", kind, name, result.ID)
	return nil
}

func findDoc(ctx context.Context, client *dt.Client, kind, name string) (*dt.Document, error) {
	docs, err := client.List(ctx, docType(kind))
	if err != nil {
		return nil, err
	}
	target := fmt.Sprintf("%s/%s", kind, name)
	for i := range docs {
		if docs[i].Name == target {
			return &docs[i], nil
		}
	}
	return nil, nil
}
