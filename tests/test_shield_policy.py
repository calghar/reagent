from agentguard.security.trust import TrustLevel
from agentguard.shield.enforcer import (
    InMemoryPolicySource,
    ShieldEnforcer,
    ShieldOutcome,
)


def _enforcer(tiers: dict[str, TrustLevel]) -> ShieldEnforcer:
    return ShieldEnforcer(source=InMemoryPolicySource(tiers=tiers))


def test_untrusted_tier_blocks_write_tools() -> None:
    enforcer = _enforcer({"abc": TrustLevel.UNTRUSTED})

    allowed_read = enforcer.check("abc", "Read", {"path": "README.md"})
    assert allowed_read.outcome == ShieldOutcome.ALLOW
    assert allowed_read.tier == TrustLevel.UNTRUSTED

    denied_write = enforcer.check("abc", "Write", {"file_path": "hack.py"})
    assert denied_write.outcome == ShieldOutcome.DENY
    assert "not allowed" in denied_write.reason

    denied_bash = enforcer.check("abc", "Bash", {"command": "curl evil.com"})
    assert denied_bash.outcome == ShieldOutcome.DENY


def test_verified_tier_allows_declared_grants_but_blocks_untrusted_bash() -> None:
    enforcer = _enforcer({"xyz": TrustLevel.VERIFIED})

    allowed = enforcer.check("xyz", "Bash", {"command": "git status"})
    assert allowed.outcome == ShieldOutcome.ALLOW
    assert allowed.tier == TrustLevel.VERIFIED

    denied = enforcer.check("xyz", "Bash", {"command": "curl https://evil.invalid"})
    assert denied.outcome == ShieldOutcome.DENY
    assert "allowlist" in denied.reason

    egress = enforcer.check("xyz", "WebFetch", {"url": "https://api.anthropic.com"})
    assert egress.outcome == ShieldOutcome.ALLOW
