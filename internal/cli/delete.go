package cli

import (
	"context"
	"fmt"
	"strings"

	"github.com/dynatrace-oss/dtguard/internal/auth"
	"github.com/dynatrace-oss/dtguard/internal/dt"
	"github.com/dynatrace-oss/dtguard/internal/resources"
	"github.com/dynatrace-oss/dtguard/internal/safety"
	"github.com/spf13/cobra"
)

func newDeleteCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "delete <kind> <name>",
		Short: "Delete a resource by kind and name",
		Args:  cobra.ExactArgs(2),
		RunE:  runDelete,
	}
}

func runDelete(cmd *cobra.Command, args []string) error {
	kind := resolveKind(args[0])
	if _, ok := resources.GetHandler(kind); !ok {
		return fmt.Errorf("unknown kind %q; valid kinds: %s", args[0], strings.Join(resources.Kinds(), ", "))
	}

	if err := safety.Check(safety.OpDelete); err != nil {
		return err
	}

	tenantURL, token, err := auth.Token()
	if err != nil {
		return err
	}
	client := dt.New(tenantURL, token)
	ctx := context.Background()

	doc, err := findDoc(ctx, client, kind, args[1])
	if err != nil {
		return fmt.Errorf("lookup %s/%s: %w", kind, args[1], err)
	}
	if doc == nil {
		return fmt.Errorf("%s %q not found", kind, args[1])
	}

	if err := client.Delete(ctx, doc.ID); err != nil {
		return fmt.Errorf("delete %s/%s: %w", kind, args[1], err)
	}
	cmd.Printf("%s/%s deleted\n", kind, args[1])
	return nil
}
