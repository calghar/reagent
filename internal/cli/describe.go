package cli

import (
	"context"
	"fmt"
	"strings"

	"github.com/dynatrace-oss/dtguard/internal/auth"
	"github.com/dynatrace-oss/dtguard/internal/dt"
	"github.com/dynatrace-oss/dtguard/internal/resources"
	"github.com/spf13/cobra"
)

func newDescribeCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "describe <kind> <name>",
		Short: "Show detailed information about a resource",
		Args:  cobra.ExactArgs(2),
		RunE:  runDescribe,
	}
}

func runDescribe(cmd *cobra.Command, args []string) error {
	kind := resolveKind(args[0])
	h, ok := resources.GetHandler(kind)
	if !ok {
		return fmt.Errorf("unknown kind %q; valid kinds: %s", args[0], strings.Join(resources.Kinds(), ", "))
	}

	tenantURL, token, err := auth.Token()
	if err != nil {
		return err
	}
	client := dt.New(tenantURL, token)
	ctx := context.Background()

	docs, err := client.List(ctx, docType(kind))
	if err != nil {
		return fmt.Errorf("list %s: %w", kind, err)
	}
	for _, doc := range docs {
		r, err := decodeDoc(kind, doc)
		if err != nil {
			continue
		}
		if r.GetMetadata().Name == args[1] {
			fields := h.DescribeFields(r)
			for _, f := range fields {
				if f.Value != "" {
					cmd.Printf("%-18s %s\n", f.Name+":", f.Value)
				}
			}
			return nil
		}
	}
	return fmt.Errorf("%s %q not found", kind, args[1])
}
