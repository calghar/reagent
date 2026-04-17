import enum
import logging
from typing import Any, Protocol

from pydantic import BaseModel

from agentguard.security.trust import TrustLevel
from agentguard.shield.policy import policy_for

logger = logging.getLogger(__name__)


class ShieldOutcome(enum.StrEnum):
    ALLOW = "allow"
    DENY = "deny"


class ShieldDecision(BaseModel):
    outcome: ShieldOutcome
    reason: str = ""
    tier: TrustLevel = TrustLevel.UNTRUSTED

    @property
    def allowed(self) -> bool:
        return self.outcome == ShieldOutcome.ALLOW


class PolicySource(Protocol):
    """Strategy for resolving a trust tier from an asset content hash."""

    def tier_for(self, asset_content_hash: str) -> TrustLevel: ...


class InMemoryPolicySource:
    """PolicySource backed by an in-memory dict. Used in tests."""

    def __init__(self, tiers: dict[str, TrustLevel] | None = None) -> None:
        self._tiers = dict(tiers or {})

    def set(self, asset_content_hash: str, tier: TrustLevel) -> None:
        self._tiers[asset_content_hash] = tier

    def tier_for(self, asset_content_hash: str) -> TrustLevel:
        return self._tiers.get(asset_content_hash, TrustLevel.UNTRUSTED)


class AttestationPolicySource:
    """PolicySource that reads the trust tier from the AttestationStore."""

    def __init__(self, store: Any | None = None) -> None:
        # Lazy-import to keep shield/__init__.py light.
        from agentguard.attestation.store import AttestationStore

        self._store = store or AttestationStore()

    def tier_for(self, asset_content_hash: str) -> TrustLevel:
        record = self._store.get_by_asset_hash(asset_content_hash)
        return record.trust_level if record else TrustLevel.UNTRUSTED


class TrustStorePolicySource:
    """PolicySource that reads the current tier from the TrustStore.

    The TrustStore is the authoritative source for the *current* tier; the
    AttestationStore only records the tier frozen at signing time, which does
    not reflect later ``trust promote`` or ``trust demote`` actions.
    """

    def __init__(self, store: Any | None = None) -> None:
        from agentguard.config import AgentGuardConfig
        from agentguard.security.trust import TrustStore

        if store is None:
            cfg = AgentGuardConfig()
            trust_path = cfg.catalog.path.parent / "trust.jsonl"
            store = TrustStore(trust_path)
            store.load()
        self._store = store

    def tier_for(self, asset_content_hash: str) -> TrustLevel:
        record = self._store.get_by_content_hash(asset_content_hash)
        return record.trust_level if record else TrustLevel.UNTRUSTED


class CompositePolicySource:
    """Resolve tier from the first source that has a record for the hash.

    Default ordering: TrustStore (current tier) then AttestationStore (tier
    frozen at signing). Returns UNTRUSTED if no source has a record.
    """

    def __init__(self, sources: list[PolicySource] | None = None) -> None:
        if sources is None:
            sources = [TrustStorePolicySource(), AttestationPolicySource()]
        self._sources = sources

    def tier_for(self, asset_content_hash: str) -> TrustLevel:
        for source in self._sources:
            tier = source.tier_for(asset_content_hash)
            if tier != TrustLevel.UNTRUSTED:
                return tier
        return TrustLevel.UNTRUSTED


class ShieldEnforcer:
    """Evaluates whether a tool call is permitted under the asset's trust tier."""

    def __init__(self, source: PolicySource | None = None) -> None:
        self._source = source or CompositePolicySource()

    def check(
        self,
        asset_content_hash: str,
        tool_name: str,
        tool_args: dict[str, Any] | None = None,
    ) -> ShieldDecision:
        """Return a ``ShieldDecision`` for a proposed tool invocation.

        Args:
            asset_content_hash: SHA-256 of the asset in scope for this call.
            tool_name: Tool identifier as reported by the harness.
            tool_args: Tool arguments, used for Bash command-prefix checks
                and write-path checks.

        Returns:
            Decision with outcome, reason, and the resolved trust tier.
        """
        tier = self._source.tier_for(asset_content_hash)
        policy = policy_for(tier)
        args = tool_args or {}

        if tool_name not in policy.allowed_tools:
            return ShieldDecision(
                outcome=ShieldOutcome.DENY,
                reason=f"tool {tool_name!r} not allowed for tier {tier.name}",
                tier=tier,
            )

        if tool_name == "Bash":
            decision = self._check_bash(args, policy, tier)
            if decision:
                return decision

        if tool_name in {"WebFetch", "WebSearch"} and not policy.allow_external_egress:
            return ShieldDecision(
                outcome=ShieldOutcome.DENY,
                reason=f"external egress not permitted for tier {tier.name}",
                tier=tier,
            )

        if (
            tool_name in {"Write", "Edit", "MultiEdit", "NotebookEdit"}
            and not policy.allow_file_writes
        ):
            return ShieldDecision(
                outcome=ShieldOutcome.DENY,
                reason=f"file writes not permitted for tier {tier.name}",
                tier=tier,
            )

        return ShieldDecision(outcome=ShieldOutcome.ALLOW, tier=tier)

    @staticmethod
    def _check_bash(
        args: dict[str, Any],
        policy: Any,
        tier: TrustLevel,
    ) -> ShieldDecision | None:
        if not policy.allow_bash:
            return ShieldDecision(
                outcome=ShieldOutcome.DENY,
                reason=f"Bash not permitted for tier {tier.name}",
                tier=tier,
            )
        if not policy.bash_allowlist_prefixes:
            return None
        cmd = str(args.get("command", "")).lstrip()
        if not any(cmd.startswith(p) for p in policy.bash_allowlist_prefixes):
            return ShieldDecision(
                outcome=ShieldOutcome.DENY,
                reason=(f"Bash command does not match allowlist for tier {tier.name}"),
                tier=tier,
            )
        return None
