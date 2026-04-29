package cli

import (
	"github.com/dynatrace-oss/dtguard/internal/auth"
	"github.com/dynatrace-oss/dtguard/internal/output"
	"github.com/spf13/cobra"
)

// Stubs for the verb-noun command tree. Each command will be fleshed out in
// subsequent batches per the implementation plan.

func notImplemented(use string) *cobra.Command {
	return &cobra.Command{
		Use:   use,
		Short: "(not implemented)",
		RunE: func(cmd *cobra.Command, args []string) error {
			cmd.Println("not implemented yet")
			return nil
		},
	}
}

func newAuthCmd() *cobra.Command {
	c := &cobra.Command{Use: "auth", Short: "Inspect the active dtctl authentication context"}
	login := &cobra.Command{
		Use:   "login",
		Short: "Authenticate via dtctl",
		RunE: func(cmd *cobra.Command, args []string) error {
			cmd.Println("dtguard delegates auth to dtctl. Run: dtctl auth login")
			return nil
		},
	}
	logout := &cobra.Command{
		Use:   "logout",
		Short: "Sign out via dtctl",
		RunE: func(cmd *cobra.Command, args []string) error {
			cmd.Println("dtguard delegates auth to dtctl. Run: dtctl auth logout")
			return nil
		},
	}
	c.AddCommand(login, logout, newWhoamiCmd("whoami"), newWhoamiCmd("status"))
	return c
}

func newWhoamiCmd(use string) *cobra.Command {
	return &cobra.Command{
		Use:   use,
		Short: "Show the active dtctl context",
		RunE: func(cmd *cobra.Command, args []string) error {
			id, err := auth.Current()
			if err != nil {
				return err
			}
			return output.FromCmd(cmd).Print(id)
		},
	}
}

func newConfigCmd() *cobra.Command {
	c := &cobra.Command{Use: "config", Short: "Manage dtguard configuration contexts"}
	c.AddCommand(notImplemented("set-context"), notImplemented("use-context"), notImplemented("view"), notImplemented("get-contexts"))
	return c
}

// newGetCmd, newDescribeCmd, newApplyCmd, newDeleteCmd live in their
// own files (get.go, describe.go, apply.go, delete.go).

func newScanCmd() *cobra.Command {
	return notImplemented("scan <path>")
}

func newSignCmd() *cobra.Command {
	return notImplemented("sign <proposal-id>")
}

func newRevokeCmd() *cobra.Command {
	return notImplemented("revoke <hash>")
}

func newCICmd() *cobra.Command {
	return notImplemented("ci")
}

func newBundleCmd() *cobra.Command {
	c := &cobra.Command{Use: "bundle", Short: "Export or verify offline attestation bundles"}
	c.AddCommand(notImplemented("export"), notImplemented("verify"))
	return c
}

func newSyncCmd() *cobra.Command {
	return notImplemented("sync")
}

func newShieldCmd() *cobra.Command {
	c := &cobra.Command{Use: "shield", Short: "Opt-in PreToolUse enforcement"}
	c.AddCommand(notImplemented("install"), notImplemented("check"), notImplemented("status"), notImplemented("sync"), notImplemented("invoke"))
	return c
}

func newDoctorCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "doctor",
		Short: "Diagnose dtguard configuration and tenant reachability",
		RunE: func(cmd *cobra.Command, args []string) error {
			id, err := auth.Current()
			if err != nil {
				cmd.Printf("auth:         FAIL (%v)\n", err)
				return err
			}
			cmd.Printf("auth:         OK (context=%s tenant=%s)\n", id.ContextName, id.TenantURL)
			if _, _, err := auth.Token(); err != nil {
				cmd.Printf("token:        FAIL (%v)\n", err)
				return err
			}
			cmd.Println("token:        OK")
			cmd.Println("signing-key:  not checked (deferred to signing batch)")
			cmd.Println("otel:         not checked (deferred to telemetry batch)")
			return nil
		},
	}
}
