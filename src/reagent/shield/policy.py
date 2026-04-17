import logging

from pydantic import BaseModel, Field

from reagent.security.trust import TrustLevel

logger = logging.getLogger(__name__)


class TrustPolicy(BaseModel):
    """Runtime tool-grant authority mapped from a TrustLevel.

    Higher tiers inherit everything the lower tier allowed. The shield
    consults this policy at invocation time to narrow or reject tool
    calls that would exceed the asset's current authority.
    """

    tier: TrustLevel
    allowed_tools: set[str] = Field(default_factory=set)
    allow_bash: bool = False
    bash_allowlist_prefixes: list[str] = Field(default_factory=list)
    allow_external_egress: bool = False
    allow_file_writes: bool = False


_UNTRUSTED = TrustPolicy(
    tier=TrustLevel.UNTRUSTED,
    allowed_tools={"Read", "Grep", "Glob"},
    allow_bash=False,
    allow_external_egress=False,
    allow_file_writes=False,
)

_REVIEWED = TrustPolicy(
    tier=TrustLevel.REVIEWED,
    allowed_tools={
        "Read",
        "Grep",
        "Glob",
        "Write",
        "Edit",
        "MultiEdit",
        "NotebookEdit",
        "Bash",
        "WebFetch",
        "WebSearch",
    },
    allow_bash=True,
    bash_allowlist_prefixes=[
        "git ",
        "npm ",
        "pnpm ",
        "yarn ",
        "python ",
        "python3 ",
        "uv ",
        "uvx ",
        "pytest",
        "ruff",
        "mypy",
        "ls",
        "cat",
        "grep",
        "find",
        "echo",
    ],
    allow_external_egress=True,
    allow_file_writes=True,
)

_VERIFIED = _REVIEWED.model_copy(update={"tier": TrustLevel.VERIFIED})

_NATIVE = TrustPolicy(
    tier=TrustLevel.NATIVE,
    allowed_tools={
        "Read",
        "Grep",
        "Glob",
        "Write",
        "Edit",
        "MultiEdit",
        "NotebookEdit",
        "Bash",
    },
    allow_bash=True,
    bash_allowlist_prefixes=[],
    allow_external_egress=False,
    allow_file_writes=True,
)

TRUST_POLICY: dict[TrustLevel, TrustPolicy] = {
    TrustLevel.UNTRUSTED: _UNTRUSTED,
    TrustLevel.REVIEWED: _REVIEWED,
    TrustLevel.VERIFIED: _VERIFIED,
    TrustLevel.NATIVE: _NATIVE,
}


def policy_for(tier: TrustLevel) -> TrustPolicy:
    """Return the ``TrustPolicy`` for ``tier``.

    Falls back to ``UNTRUSTED`` if the tier is not recognised.
    """
    return TRUST_POLICY.get(tier, _UNTRUSTED)
