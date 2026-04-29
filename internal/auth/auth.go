// Package auth is a thin wrapper over dtctl's config + token storage.
// dtguard never owns auth state: every call re-reads the active dtctl
// context so token refreshes performed by `dtctl auth login` are picked
// up immediately.
package auth

import (
	"fmt"

	dtconfig "github.com/dynatrace-oss/dtctl/pkg/config"
)

// Identity describes the active dtctl context dtguard will use.
type Identity struct {
	ContextName string
	TenantURL   string
	SafetyLevel string
	TokenRef    string
}

// Current loads the active dtctl context. Returns an actionable error
// when no context is configured or no token is bound.
func Current() (*Identity, error) {
	cfg, err := dtconfig.Load()
	if err != nil {
		return nil, fmt.Errorf("load dtctl config: %w (run `dtctl auth login`)", err)
	}
	if cfg.CurrentContext == "" {
		return nil, fmt.Errorf("no active dtctl context (run `dtctl auth login`)")
	}
	ctx, err := cfg.CurrentContextObj()
	if err != nil {
		return nil, fmt.Errorf("resolve context %q: %w", cfg.CurrentContext, err)
	}
	return &Identity{
		ContextName: cfg.CurrentContext,
		TenantURL:   ctx.Environment,
		SafetyLevel: string(ctx.GetEffectiveSafetyLevel()),
		TokenRef:    ctx.TokenRef,
	}, nil
}

// Token resolves the active context's token (keyring first, file fallback).
// Always re-reads so dtctl-side rotation is observed.
func Token() (tenantURL, token string, err error) {
	cfg, err := dtconfig.Load()
	if err != nil {
		return "", "", fmt.Errorf("load dtctl config: %w", err)
	}
	if cfg.CurrentContext == "" {
		return "", "", fmt.Errorf("no active dtctl context (run `dtctl auth login`)")
	}
	ctx, err := cfg.CurrentContextObj()
	if err != nil {
		return "", "", fmt.Errorf("resolve context %q: %w", cfg.CurrentContext, err)
	}
	tok, err := dtconfig.GetTokenWithFallback(cfg, ctx.TokenRef)
	if err != nil {
		return "", "", fmt.Errorf("resolve token %q: %w", ctx.TokenRef, err)
	}
	return ctx.Environment, tok, nil
}
