// Package output is a thin shim over dtctl's pkg/output. It routes
// command results through a single Printer chosen from the global
// -o/--output flag plus AI-agent auto-detection via pkg/aidetect; the
// --agent flag forces the agent envelope on.
package output

import (
	"io"
	"os"

	"github.com/dynatrace-oss/dtctl/pkg/aidetect"
	dtoutput "github.com/dynatrace-oss/dtctl/pkg/output"
	"github.com/spf13/cobra"
)

// FlagFormat is the long form of the -o flag.
const FlagFormat = "output"

// FlagAgent forces the agent envelope regardless of auto-detection.
const FlagAgent = "agent"

// Bind attaches --output/-o and --agent as persistent flags on cmd.
// Defaults: format "table", agent false.
func Bind(cmd *cobra.Command) {
	cmd.PersistentFlags().StringP(FlagFormat, "o", "table", "output format: table|json|yaml|csv")
	cmd.PersistentFlags().Bool(FlagAgent, false, "wrap output in the dtctl agent envelope")
}

// FromCmd builds a Printer for cmd. The agent envelope is used when
// --agent is set or when pkg/aidetect detects an AI harness.
func FromCmd(cmd *cobra.Command) dtoutput.Printer {
	format, _ := cmd.Flags().GetString(FlagFormat)
	agent, _ := cmd.Flags().GetBool(FlagAgent)
	return build(cmd.OutOrStdout(), format, agent)
}

func build(w io.Writer, format string, forceAgent bool) dtoutput.Printer {
	if w == nil {
		w = os.Stdout
	}
	if forceAgent || aidetect.Detect().Detected {
		return dtoutput.NewAgentPrinter(w, &dtoutput.ResponseContext{})
	}
	return dtoutput.NewPrinterWithWriter(format, w)
}
