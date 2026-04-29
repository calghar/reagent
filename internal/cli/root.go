package cli

import (
	"github.com/dynatrace-oss/dtguard/internal/output"
	"github.com/dynatrace-oss/dtguard/internal/version"
	"github.com/spf13/cobra"
)

func NewRootCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "dtguard",
		Short: "Attestation and observability for AI-agent configuration assets",
		Long: `dtguard fingerprints AI-agent configuration assets by content_hash,
signs the fingerprint once behavior stabilizes, and surfaces drift through
Dynatrace Davis. Aligned with dtctl on CLI shape, resource model, and auth.`,
		Version:       version.Version,
		SilenceUsage:  true,
		SilenceErrors: true,
	}
	output.Bind(cmd)

	cmd.AddCommand(
		newAuthCmd(),
		newConfigCmd(),
		newGetCmd(),
		newDescribeCmd(),
		newApplyCmd(),
		newDeleteCmd(),
		newScanCmd(),
		newSignCmd(),
		newRevokeCmd(),
		newCICmd(),
		newBundleCmd(),
		newSyncCmd(),
		newShieldCmd(),
		newDoctorCmd(),
	)

	return cmd
}
