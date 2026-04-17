from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from agentguard._tuning import get_tuning
from agentguard.core.parsers import AssetType
from agentguard.intelligence.analyzer import RepoProfile
from agentguard.llm.config import GenerationConfig, LLMConfig
from agentguard.llm.parser import GeneratedAsset, ParseError, parse_llm_response
from agentguard.llm.prompts import (
    CRITIC_SYSTEM,
    SYSTEM_PROMPTS,
    build_critic_prompt,
    build_generation_prompt,
    build_revision_prompt,
)
from agentguard.llm.providers import LLMProvider, LLMResponse

if TYPE_CHECKING:
    from agentguard.security.gate import SecurityResult

logger = logging.getLogger(__name__)

# Vacuous content patterns — bodies that are too generic to be useful
_VACUOUS_PATTERNS = [
    r"^Working in a \w+ project\.?$",
    r"^You are a \w+ specialist\.?$",
    r"^This is a \w+ (agent|skill)\.?$",
    r"^Follow project conventions\.?$",
]


class CriticResult(BaseModel):
    """Result from the critic pass."""

    score: int
    issues: list[str]
    suggestions: list[str]
    raw_response: str = ""


class QualityGateResult(BaseModel):
    """Outcome of the quality gate validation."""

    passed: bool
    errors: list[str]
    warnings: list[str]


class GenerationResult(BaseModel):
    """Full result from the adversarial generation pipeline."""

    asset: GeneratedAsset
    response: LLMResponse
    critic: CriticResult | None = None
    revision_response: LLMResponse | None = None
    quality: QualityGateResult
    # SecurityResult | None — typed as Any to avoid circular import at class
    # creation time; the value is always None or a SecurityResult instance.
    security_result: Any = None
    total_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0


def _check_vacuous_content(body: str) -> list[str]:
    """Check for vacuous/generic body content."""
    errors: list[str] = []
    lines = [line.strip() for line in body.strip().splitlines() if line.strip()]
    # Check if the body is *only* vacuous content (a few lines, all generic)
    if len(lines) <= 3:
        for line in lines:
            clean = re.sub(r"^#+\s*", "", line)  # strip headings
            for pattern in _VACUOUS_PATTERNS:
                if re.match(pattern, clean):
                    errors.append(f"Vacuous content detected: {clean!r}")
    return errors


VALID_TOOL_NAMES = {
    "Read",
    "Write",
    "Edit",
    "Bash",
    "Glob",
    "Grep",
    "Agent",
    "WebFetch",
    "WebSearch",
    "Task",
}


def _check_tools(fm: dict[str, object], asset_type: AssetType) -> list[str]:
    """Validate tool names in frontmatter."""
    warnings: list[str] = []
    tools_key = "tools" if asset_type == AssetType.AGENT else "allowed-tools"
    tools = fm.get(tools_key)
    if isinstance(tools, list):
        for tool in tools:
            tool_name = str(tool).split("(")[0]  # Agent(type) syntax
            if tool_name not in VALID_TOOL_NAMES:
                warnings.append(f"Unknown tool: {tool_name}")
    return warnings


def validate_quality(asset: GeneratedAsset) -> QualityGateResult:
    """Run quality gate checks on a generated asset.

    Checks:
    - Non-empty body (for non-hook assets)
    - No vacuous content
    - Valid tool names
    - Frontmatter completeness

    Args:
        asset: The generated asset to validate.

    Returns:
        QualityGateResult with pass/fail status and details.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Body checks (hooks and commands get a pass on some checks)
    if asset.asset_type not in (AssetType.HOOK, AssetType.COMMAND):
        if not asset.body.strip():
            errors.append("Empty body")
        else:
            errors.extend(_check_vacuous_content(asset.body))

    # Tool validation
    warnings.extend(_check_tools(asset.frontmatter, asset.asset_type))

    return QualityGateResult(
        passed=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


def _parse_critic_response(text: str) -> CriticResult:
    """Parse the critic's JSON response, handling LLM quirks."""
    # Try to extract JSON from the response
    # LLMs sometimes wrap JSON in code fences
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    json_text = json_match.group(1) if json_match else text.strip()

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        # Fallback: try to find any JSON object in the text
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if not brace_match:
            return CriticResult(
                score=5,
                issues=["Critic response was not valid JSON"],
                suggestions=[],
                raw_response=text,
            )
        try:
            data = json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            return CriticResult(
                score=5,
                issues=["Critic response was not valid JSON"],
                suggestions=[],
                raw_response=text,
            )

    return CriticResult(
        score=max(1, min(10, int(data.get("score", 5)))),
        issues=data.get("issues", []),
        suggestions=data.get("suggestions", []),
        raw_response=text,
    )


async def run_critic(
    asset: GeneratedAsset,
    provider: LLMProvider,
    config: GenerationConfig | None = None,
) -> tuple[CriticResult, LLMResponse]:
    """Run the critic pass on a generated asset.

    Args:
        asset: The generated asset to critique.
        provider: LLM provider for the critic call.
        config: Generation config overrides.

    Returns:
        Tuple of (CriticResult, LLMResponse).
    """
    content = _asset_to_text(asset)
    prompt = build_critic_prompt(content, asset.asset_type)
    gen_config = config or GenerationConfig(max_output_tokens=1024)

    response = await provider.generate(
        prompt=prompt,
        system=CRITIC_SYSTEM,
        config=gen_config,
    )
    result = _parse_critic_response(response.text)
    return result, response


def _asset_to_text(asset: GeneratedAsset) -> str:
    """Convert a GeneratedAsset back to text for critic input."""
    if not asset.frontmatter:
        return asset.body

    import yaml

    fm_text = yaml.dump(
        asset.frontmatter,
        default_flow_style=False,
        sort_keys=False,
    ).strip()
    return f"---\n{fm_text}\n---\n{asset.body}"


async def _run_security_pass(
    security_gate: object,
    asset: GeneratedAsset,
    asset_type: AssetType,
    user_prompt: str,
    system: str,
    gen_config: GenerationConfig,
    provider: LLMProvider,
    llm_config: LLMConfig,
    repo_path: Path,
) -> SecurityResult | None:
    """Run the security gate pass and optionally trigger a security revision.

    If the gate grade is below C and the critic feature is enabled, generates
    a security-focused revision and re-scans.

    Args:
        security_gate: A ``SecurityGate`` instance (typed as object to avoid
            import at module level).
        asset: The asset to scan (may be updated by revision).
        asset_type: Asset type for revision parsing.
        user_prompt: Original generation prompt for revision context.
        system: System prompt for the provider.
        gen_config: Generation config for revision call.
        provider: LLM provider for revision generation.
        llm_config: LLM config flags.
        repo_path: Repo root for temp file creation.

    Returns:
        Final SecurityResult after any revision, or ``None`` on error.
    """
    from agentguard.security.gate import SecurityGate

    if not isinstance(security_gate, SecurityGate):
        return None

    security_result = await security_gate.check(asset, repo_path)
    if security_result is None:
        return None

    if security_result.passed or not llm_config.features.use_critic:
        return security_result

    # Attempt a security-focused revision
    revised = await _apply_security_revision(
        asset=asset,
        asset_type=asset_type,
        security_result=security_result,
        user_prompt=user_prompt,
        system=system,
        gen_config=gen_config,
        provider=provider,
        security_gate=security_gate,
        repo_path=repo_path,
    )
    return revised if revised is not None else security_result


async def _apply_security_revision(
    asset: GeneratedAsset,
    asset_type: AssetType,
    security_result: SecurityResult,
    user_prompt: str,
    system: str,
    gen_config: GenerationConfig,
    provider: LLMProvider,
    security_gate: object,
    repo_path: Path,
) -> SecurityResult | None:
    """Generate a security-focused revision and re-scan the result.

    Args:
        asset: Current asset (may have security issues).
        asset_type: Asset type for parsing the revision response.
        security_result: The failing SecurityResult.
        user_prompt: Original prompt for context.
        system: System prompt.
        gen_config: Generation configuration.
        provider: LLM provider.
        security_gate: SecurityGate instance.
        repo_path: Repo root for temp file creation.

    Returns:
        New SecurityResult after the revision, or ``None`` if revision failed.
    """
    from agentguard.security.gate import SecurityGate

    security_issues_text = "\n".join(
        f"- [{i.severity.upper()}] {i.message}" for i in security_result.issues
    )
    logger.debug("Triggering security revision for issues:\n%s", security_issues_text)

    revision_prompt = build_revision_prompt(
        user_prompt,
        _asset_to_text(asset),
        3,  # Low score to signal major issues
        [f"Security issue: {i.message}" for i in security_result.issues],
        [f"Fix: remove or restrict {i.rule_id}" for i in security_result.issues],
    )
    sec_revision_response = await provider.generate(
        prompt=revision_prompt,
        system=system,
        config=gen_config,
    )

    try:
        revised_asset = parse_llm_response(sec_revision_response.text, asset_type)
    except ParseError:
        logger.warning("Security revision parse failed, keeping original")
        return None

    if not isinstance(security_gate, SecurityGate):
        return None

    return await security_gate.check(revised_asset, repo_path)


async def generate_with_quality(
    asset_type: AssetType,
    name: str,
    profile: RepoProfile,
    provider: LLMProvider,
    llm_config: LLMConfig,
    *,
    evaluation_context: str | None = None,
    telemetry_context: str | None = None,
    critic_provider: LLMProvider | None = None,
    security_gate: object | None = None,
    repo_path: Path | None = None,
) -> GenerationResult:
    """Run the full adversarial generation pipeline.

    1. Generate asset with LLM
    2. Parse response
    3. Optionally critique with cheap model
    4. Revise if score < threshold
    5. Validate with quality gate
    6. Optionally run security gate

    Args:
        asset_type: Target asset type.
        name: Asset name.
        profile: Repository profile.
        provider: Primary LLM provider for generation.
        llm_config: LLM configuration.
        evaluation_context: Optional evaluation summary.
        telemetry_context: Optional telemetry summary.
        critic_provider: Optional separate provider for critic.
        security_gate: Optional SecurityGate instance for post-generation scan.
        repo_path: Repository root for the security gate temp files.

    Returns:
        GenerationResult with asset, quality check, and cost info.
    """
    gen_config = GenerationConfig(
        temperature=llm_config.temperature,
        max_output_tokens=llm_config.max_output_tokens,
    )

    system = SYSTEM_PROMPTS.get(asset_type, "")
    user_prompt = build_generation_prompt(
        asset_type,
        name,
        profile,
        evaluation_context=evaluation_context,
        telemetry_context=telemetry_context,
        max_prompt_tokens=llm_config.max_prompt_tokens,
    )

    # Pass 1: Generate
    response = await provider.generate(
        prompt=user_prompt,
        system=system,
        config=gen_config,
    )

    total_cost = response.cost_usd
    total_in = response.input_tokens
    total_out = response.output_tokens

    asset = parse_llm_response(response.text, asset_type)

    # Pass 2-3: Critic + optional revision
    critic_result: CriticResult | None = None
    revision_response: LLMResponse | None = None

    if llm_config.features.use_critic:
        critic_prov = critic_provider or provider
        critic_result, critic_resp = await run_critic(
            asset, critic_prov, GenerationConfig(max_output_tokens=1024)
        )
        total_cost += critic_resp.cost_usd
        total_in += critic_resp.input_tokens
        total_out += critic_resp.output_tokens

        # Revise if score is below threshold
        if critic_result.score < get_tuning().evaluation.critic_revision_threshold:
            revision_prompt = build_revision_prompt(
                user_prompt,
                _asset_to_text(asset),
                critic_result.score,
                critic_result.issues,
                critic_result.suggestions,
            )
            revision_response = await provider.generate(
                prompt=revision_prompt,
                system=system,
                config=gen_config,
            )
            total_cost += revision_response.cost_usd
            total_in += revision_response.input_tokens
            total_out += revision_response.output_tokens

            try:
                asset = parse_llm_response(revision_response.text, asset_type)
            except ParseError:
                logger.warning("Revision parse failed, keeping original")

    # Pass 4: Quality gate
    quality = validate_quality(asset)

    # Pass 5: Security gate (optional)
    security_result: SecurityResult | None = None
    if security_gate is not None:
        security_result = await _run_security_pass(
            security_gate,
            asset,
            asset_type,
            user_prompt,
            system,
            gen_config,
            provider,
            llm_config,
            repo_path or Path.cwd(),
        )

    return GenerationResult(
        asset=asset,
        response=response,
        critic=critic_result,
        revision_response=revision_response,
        quality=quality,
        security_result=security_result,
        total_cost_usd=total_cost,
        total_input_tokens=total_in,
        total_output_tokens=total_out,
    )
