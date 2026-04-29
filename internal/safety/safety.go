// Package safety wraps dtctl's pkg/safety so dtguard reuses the same
// four-level model (readonly | readwrite-mine | readwrite-all |
// dangerously-unrestricted). Ownership is treated as unknown:
// dtguard does not yet model resource ownership, so update/delete
// requires at least readwrite-all.
package safety

import (
	"fmt"

	dtconfig "github.com/dynatrace-oss/dtctl/pkg/config"
	dtsafety "github.com/dynatrace-oss/dtctl/pkg/safety"
)

// Op aliases dtctl's safety operation enum.
type Op = dtsafety.Operation

// Operation constants re-exported for callers.
const (
	OpRead         = dtsafety.OperationRead
	OpCreate       = dtsafety.OperationCreate
	OpUpdate       = dtsafety.OperationUpdate
	OpDelete       = dtsafety.OperationDelete
	OpDeleteBucket = dtsafety.OperationDeleteBucket
)

// Check returns nil if op is allowed under the active dtctl context's
// safety level, or a typed *dtsafety.SafetyError otherwise.
func Check(op Op) error {
	cfg, err := dtconfig.Load()
	if err != nil {
		return fmt.Errorf("load dtctl config: %w", err)
	}
	if cfg.CurrentContext == "" {
		return fmt.Errorf("no active dtctl context (run `dtctl auth login`)")
	}
	ctx, err := cfg.CurrentContextObj()
	if err != nil {
		return fmt.Errorf("resolve context %q: %w", cfg.CurrentContext, err)
	}
	return dtsafety.NewChecker(cfg.CurrentContext, ctx).CheckError(op, dtsafety.OwnershipUnknown)
}
