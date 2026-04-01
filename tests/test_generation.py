from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from reagent.core.parsers import AssetType
from reagent.intelligence.analyzer import (
    DetectedTestConfig,
    LintConfig,
    RepoProfile,
)
from reagent.llm.config import LLMConfig
from reagent.llm.parser import (
    GeneratedAsset,
    ParseError,
    parse_llm_response,
    split_frontmatter,
)
from reagent.llm.prompts import (
    SYSTEM_PROMPTS,
    build_critic_prompt,
    build_generation_prompt,
    build_revision_prompt,
)
from reagent.llm.providers import LLMResponse
from reagent.llm.quality import (
    _parse_critic_response,
    validate_quality,
)


@pytest.fixture()
def python_profile() -> RepoProfile:
    return RepoProfile(
        repo_path="/tmp/test",  # noqa: S108
        repo_name="test-repo",
        languages=["python"],
        primary_language="python",
        frameworks=["fastapi"],
        build_system="hatch",
        package_manager="uv",
        architecture="single-app",
        test_config=DetectedTestConfig(
            runner="pytest",
            command="uv run pytest",
            test_dir="tests",
        ),
        lint_configs=[
            LintConfig(tool="ruff", command="ruff check"),
            LintConfig(tool="mypy", command="mypy src/"),
        ],
        has_ci=True,
        ci_system="github-actions",
        has_docker=True,
        has_env_file=True,
        has_api_routes=True,
        conventions={"line_length": "88", "naming": "snake_case"},
        entry_points=["src/app/main.py"],
    )


class TestSystemPrompts:
    def test_all_asset_types_have_system_prompts(self) -> None:
        expected = {
            AssetType.AGENT,
            AssetType.SKILL,
            AssetType.HOOK,
            AssetType.COMMAND,
            AssetType.RULE,
            AssetType.CLAUDE_MD,
        }
        assert expected == set(SYSTEM_PROMPTS.keys())

    def test_agent_system_prompt_has_schema(self) -> None:
        prompt = SYSTEM_PROMPTS[AssetType.AGENT]
        assert "name:" in prompt
        assert "description:" in prompt
        assert "tools:" in prompt

    def test_skill_system_prompt_has_schema(self) -> None:
        prompt = SYSTEM_PROMPTS[AssetType.SKILL]
        assert "allowed-tools:" in prompt
        assert "$ARGUMENTS" in prompt


class TestBuildGenerationPrompt:
    def test_includes_repo_name(self, python_profile: RepoProfile) -> None:
        prompt = build_generation_prompt(
            AssetType.AGENT, "code-reviewer", python_profile
        )
        assert "test-repo" in prompt

    def test_includes_all_lint_configs(self, python_profile: RepoProfile) -> None:
        prompt = build_generation_prompt(
            AssetType.AGENT, "code-reviewer", python_profile
        )
        assert "ruff check" in prompt
        assert "mypy src/" in prompt

    def test_includes_test_command(self, python_profile: RepoProfile) -> None:
        prompt = build_generation_prompt(
            AssetType.AGENT, "code-reviewer", python_profile
        )
        assert "uv run pytest" in prompt

    def test_includes_conventions(self, python_profile: RepoProfile) -> None:
        prompt = build_generation_prompt(
            AssetType.AGENT, "code-reviewer", python_profile
        )
        assert "88" in prompt
        assert "snake_case" in prompt

    def test_includes_frameworks(self, python_profile: RepoProfile) -> None:
        prompt = build_generation_prompt(AssetType.AGENT, "api-dev", python_profile)
        assert "fastapi" in prompt

    def test_evaluation_context_included(self, python_profile: RepoProfile) -> None:
        prompt = build_generation_prompt(
            AssetType.AGENT,
            "test",
            python_profile,
            evaluation_context="Score: 45/100, needs more specificity",
        )
        assert "Score: 45/100" in prompt

    def test_telemetry_context_included(self, python_profile: RepoProfile) -> None:
        prompt = build_generation_prompt(
            AssetType.SKILL,
            "ci-check",
            python_profile,
            telemetry_context="Used 3x/week, 2 corrections",
        )
        assert "Used 3x/week" in prompt

    def test_output_format_instructions(self, python_profile: RepoProfile) -> None:
        prompt = build_generation_prompt(AssetType.AGENT, "test", python_profile)
        assert "YAML frontmatter" in prompt
        assert "No explanations" in prompt


class TestBuildCriticPrompt:
    def test_includes_asset_content(self) -> None:
        prompt = build_critic_prompt("---\nname: test\n---\nBody", AssetType.AGENT)
        assert "name: test" in prompt
        assert "Body" in prompt

    def test_requests_json_response(self) -> None:
        prompt = build_critic_prompt("content", AssetType.SKILL)
        assert "JSON" in prompt


class TestBuildRevisionPrompt:
    def test_includes_feedback(self) -> None:
        prompt = build_revision_prompt(
            "original prompt",
            "asset content",
            4,
            ["Issue 1", "Issue 2"],
            ["Suggestion A"],
        )
        assert "scored 4/10" in prompt
        assert "Issue 1" in prompt
        assert "Issue 2" in prompt
        assert "Suggestion A" in prompt


class TestSplitFrontmatter:
    def test_standard_format(self) -> None:
        text = "---\nname: test\ndescription: hello\n---\n# Body"
        fm, body = split_frontmatter(text)
        assert fm["name"] == "test"
        assert fm["description"] == "hello"
        assert body == "# Body"

    def test_no_frontmatter(self) -> None:
        text = "# Just a body"
        fm, body = split_frontmatter(text)
        assert fm == {}
        assert body == "# Just a body"

    def test_empty_body(self) -> None:
        text = "---\nname: test\n---"
        fm, body = split_frontmatter(text)
        assert fm["name"] == "test"
        assert body == ""

    def test_invalid_yaml(self) -> None:
        text = "---\n: invalid: yaml: [[\n---\nBody"
        with pytest.raises(ParseError):
            split_frontmatter(text)

    def test_multiline_body(self) -> None:
        text = "---\nname: x\n---\nLine 1\nLine 2\nLine 3"
        fm, body = split_frontmatter(text)
        assert fm["name"] == "x"
        assert "Line 1" in body
        assert "Line 3" in body


class TestParseResponse:
    def test_clean_response(self) -> None:
        text = "---\nname: test-agent\ndescription: A test\n---\n# Test Agent\nBody"
        result = parse_llm_response(text, AssetType.AGENT)
        assert result.frontmatter["name"] == "test-agent"
        assert "# Test Agent" in result.body

    def test_code_fenced_response(self) -> None:
        text = "```markdown\n---\nname: x\ndescription: y\n---\n# X\nBody\n```"
        result = parse_llm_response(text, AssetType.AGENT)
        assert result.frontmatter["name"] == "x"

    def test_explanation_before_frontmatter(self) -> None:
        text = "Here is the agent:\n---\nname: x\ndescription: y\n---\n# Body"
        result = parse_llm_response(text, AssetType.AGENT)
        assert result.frontmatter["name"] == "x"

    def test_empty_response_raises(self) -> None:
        with pytest.raises(ParseError, match="Empty"):
            parse_llm_response("", AssetType.AGENT)

    def test_missing_required_field(self) -> None:
        text = "---\nname: test\n---\n# Body"
        with pytest.raises(ParseError, match="description"):
            parse_llm_response(text, AssetType.AGENT)

    def test_hook_type_is_json(self) -> None:
        text = '{"hooks": {"PostToolUse": []}}'
        result = parse_llm_response(text, AssetType.HOOK)
        assert result.body == text.strip()
        assert result.frontmatter == {}

    def test_claude_md_no_frontmatter(self) -> None:
        text = "# My Project\n\n## Stack\n- Python"
        result = parse_llm_response(text, AssetType.CLAUDE_MD)
        assert "# My Project" in result.body

    def test_raw_response_preserved(self) -> None:
        text = "---\nname: x\ndescription: d\n---\n# Body"
        result = parse_llm_response(text, AssetType.AGENT)
        assert result.raw_response == text

    def test_invalid_model_in_frontmatter(self) -> None:
        text = "---\nname: x\ndescription: d\nmodel: invalid-xyz\n---\n# Body"
        with pytest.raises(ParseError, match="model"):
            parse_llm_response(text, AssetType.AGENT)

    def test_valid_model_passes(self) -> None:
        text = "---\nname: x\ndescription: d\nmodel: sonnet\n---\n# Body"
        result = parse_llm_response(text, AssetType.AGENT)
        assert result.frontmatter["model"] == "sonnet"

    def test_skill_name_too_long(self) -> None:
        long_name = "a" * 65
        text = f"---\nname: {long_name}\ndescription: d\n---\n# Body"
        with pytest.raises(ParseError, match="64"):
            parse_llm_response(text, AssetType.SKILL)

    def test_skill_name_invalid_chars(self) -> None:
        text = "---\nname: My Skill!\ndescription: d\n---\n# Body"
        with pytest.raises(ParseError, match="lowercase"):
            parse_llm_response(text, AssetType.SKILL)


class TestValidateQuality:
    def test_good_asset_passes(self) -> None:
        asset = GeneratedAsset(
            asset_type=AssetType.AGENT,
            frontmatter={"name": "test", "description": "A test agent"},
            body="# Test Agent\n\n## Responsibilities\n- Do things",
            raw_response="",
        )
        result = validate_quality(asset)
        assert result.passed

    def test_empty_body_fails(self) -> None:
        asset = GeneratedAsset(
            asset_type=AssetType.AGENT,
            frontmatter={"name": "test"},
            body="",
            raw_response="",
        )
        result = validate_quality(asset)
        assert not result.passed
        assert any("Empty body" in e for e in result.errors)

    def test_vacuous_body_fails(self) -> None:
        asset = GeneratedAsset(
            asset_type=AssetType.AGENT,
            frontmatter={"name": "test"},
            body="Working in a Python project.",
            raw_response="",
        )
        result = validate_quality(asset)
        assert not result.passed
        assert any("Vacuous" in e for e in result.errors)

    def test_hook_empty_body_passes(self) -> None:
        """Hooks don't need a body (they're JSON)."""
        asset = GeneratedAsset(
            asset_type=AssetType.HOOK,
            frontmatter={},
            body="",
            raw_response="",
        )
        result = validate_quality(asset)
        assert result.passed

    def test_unknown_tool_warns(self) -> None:
        asset = GeneratedAsset(
            asset_type=AssetType.AGENT,
            frontmatter={"name": "t", "tools": ["Read", "FakeTool"]},
            body="# Agent\nDoes stuff with multiple steps and tasks",
            raw_response="",
        )
        result = validate_quality(asset)
        assert any("FakeTool" in w for w in result.warnings)


class TestParseCriticResponse:
    def test_clean_json(self) -> None:
        text = '{"score": 8, "issues": ["minor"], "suggestions": ["add test step"]}'
        result = _parse_critic_response(text)
        assert result.score == 8
        assert result.issues == ["minor"]

    def test_json_in_code_fence(self) -> None:
        text = '```json\n{"score": 6, "issues": [], "suggestions": []}\n```'
        result = _parse_critic_response(text)
        assert result.score == 6

    def test_json_with_explanation(self) -> None:
        text = 'Here is my evaluation:\n{"score": 9, "issues": [], "suggestions": []}'
        result = _parse_critic_response(text)
        assert result.score == 9

    def test_invalid_json_fallback(self) -> None:
        text = "This is not json at all"
        result = _parse_critic_response(text)
        assert result.score == 5  # default fallback

    def test_score_clamped(self) -> None:
        text = '{"score": 15, "issues": [], "suggestions": []}'
        result = _parse_critic_response(text)
        assert result.score == 10

    def test_score_min_clamped(self) -> None:
        text = '{"score": -5, "issues": [], "suggestions": []}'
        result = _parse_critic_response(text)
        assert result.score == 1


class TestClassifyTools:
    def test_reviewer_gets_read_only(self) -> None:
        from reagent.creation.generators import classify_tools

        tools = classify_tools("code-reviewer")
        assert "Read" in tools
        assert "Write" not in tools

    def test_developer_gets_read_write(self) -> None:
        from reagent.creation.generators import classify_tools

        tools = classify_tools("backend-developer")
        assert "Write" in tools
        assert "Edit" in tools

    def test_tester_gets_execute(self) -> None:
        from reagent.creation.generators import classify_tools

        tools = classify_tools("test-runner")
        assert "Bash" in tools

    def test_refactorer_gets_edit(self) -> None:
        from reagent.creation.generators import classify_tools

        tools = classify_tools("code-simplifier")
        assert "Edit" in tools

    def test_unknown_defaults_to_read_write(self) -> None:
        from reagent.creation.generators import classify_tools

        tools = classify_tools("mystery-thing")
        assert "Read" in tools
        assert "Write" in tools

    def test_description_influences_classification(self) -> None:
        from reagent.creation.generators import classify_tools

        tools = classify_tools("helper", "Reviews code for quality")
        assert "Read" in tools
        # Review = read_only category, no Write
        assert "Write" not in tools

    def test_deploy_gets_execute(self) -> None:
        from reagent.creation.generators import classify_tools

        tools = classify_tools("deployer")
        assert "Bash" in tools


class TestCompressProfile:
    def test_includes_all_fields(self, python_profile: RepoProfile) -> None:
        from reagent.creation.generators import compress_profile

        params = compress_profile(python_profile)
        assert params["language"] == "python"
        assert "fastapi" in params["framework"]
        assert params["test_command"] == "uv run pytest"
        assert "ruff check" in params["lint_commands"]
        assert "mypy src/" in params["lint_commands"]
        assert params["package_manager"] == "uv"
        assert params["ci_system"] == "github-actions"
        assert params["line_length"] == "88"


class TestEnhancedTemplates:
    def test_agent_includes_all_lint_configs(self, python_profile: RepoProfile) -> None:
        from reagent.creation.generators import generate_agent

        content = generate_agent("test-runner", python_profile)
        assert "ruff check" in content
        assert "mypy" in content

    def test_skill_has_arguments(self, python_profile: RepoProfile) -> None:
        from reagent.creation.generators import generate_skill

        content = generate_skill("generic-helper", python_profile)
        assert "$ARGUMENTS" in content

    def test_skill_no_vacuous_default(self, python_profile: RepoProfile) -> None:
        from reagent.creation.generators import generate_skill

        content = generate_skill("generic-helper", python_profile)
        assert "Working in a python project" not in content

    def test_claude_md_includes_all_linters(self, python_profile: RepoProfile) -> None:
        from reagent.creation.generators import generate_claude_md

        content = generate_claude_md(python_profile)
        assert "ruff check" in content
        assert "mypy" in content

    def test_agent_classification_tools(self, python_profile: RepoProfile) -> None:
        from reagent.creation.generators import generate_agent

        content = generate_agent("code-reviewer", python_profile)
        assert "Read" in content
        # Reviewer should be read-only
        assert "tools:" in content


class TestLLMFallback:
    def test_create_asset_with_no_llm(
        self, tmp_path: Path, python_profile: RepoProfile
    ):
        """--no-llm flag uses templates directly."""
        from reagent.creation.creator import create_asset

        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "pyproject.toml").write_text("[project]\nname='test'\n")

        draft = create_asset(
            "agent",
            repo,
            name="test-dev",
            profile=python_profile,
            no_llm=True,
        )
        assert draft.content
        assert "test-dev" in draft.content

    def test_create_asset_fallback_on_no_provider(
        self, tmp_path: Path, python_profile: RepoProfile
    ):
        """Without API key configured, falls back to templates."""
        from reagent.creation.creator import create_asset

        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "pyproject.toml").write_text("[project]\nname='test'\n")

        # No API keys set → LLM unavailable → template fallback
        with patch.dict("os.environ", {}, clear=False):
            draft = create_asset(
                "agent",
                repo,
                name="my-agent",
                profile=python_profile,
            )
        assert draft.content
        assert "my-agent" in draft.content


class TestAdversarialPipeline:
    @pytest.mark.anyio()
    async def test_generate_with_quality_mocked(self, python_profile: RepoProfile):
        """Test the full pipeline with mocked provider."""
        from reagent.llm.quality import generate_with_quality

        mock_provider = AsyncMock()
        mock_provider.name = "mock"
        mock_provider.available = True
        mock_provider.generate.return_value = LLMResponse(
            text=(
                "---\nname: test-agent\n"
                "description: A test agent for Python\n"
                "tools:\n  - Read\n  - Grep\n---\n"
                "# Test Agent\n\n"
                "## Responsibilities\n"
                "- Review code for correctness\n"
                "- Check test coverage\n\n"
                "## Constraints\n"
                "- Never commit secrets\n"
            ),
            model="test-model",
            provider="mock",
            input_tokens=100,
            output_tokens=200,
            cost_usd=0.005,
            latency_ms=500,
            finish_reason="stop",
        )

        config = LLMConfig(features=LLMConfig().features)
        config.features.use_critic = False

        result = await generate_with_quality(
            AssetType.AGENT,
            "test-agent",
            python_profile,
            mock_provider,
            config,
        )

        assert result.quality.passed
        assert result.asset.frontmatter["name"] == "test-agent"
        assert result.total_cost_usd == pytest.approx(0.005)
        assert result.critic is None

    @pytest.mark.anyio()
    async def test_pipeline_with_critic(self, python_profile: RepoProfile) -> None:
        """Test pipeline with critic enabled and revision triggered."""
        from reagent.llm.quality import generate_with_quality

        # First call: generation, second: critic, third: revision
        mock_provider = AsyncMock()
        mock_provider.name = "mock"
        mock_provider.available = True

        gen_response = LLMResponse(
            text=(
                "---\nname: test\ndescription: A test\n---\n"
                "# Test\n\nBasic body with steps"
            ),
            model="m",
            provider="mock",
            input_tokens=100,
            output_tokens=100,
            cost_usd=0.003,
            latency_ms=400,
            finish_reason="stop",
        )
        critic_response = LLMResponse(
            text=(
                '{"score": 5, "issues": ["Too generic"],'
                ' "suggestions": ["Add specifics"]}'
            ),
            model="m",
            provider="mock",
            input_tokens=50,
            output_tokens=50,
            cost_usd=0.001,
            latency_ms=200,
            finish_reason="stop",
        )
        revision_response = LLMResponse(
            text=(
                "---\nname: test\ndescription: A test\n---\n"
                "# Test\n\n## Responsibilities\n- Specific task"
            ),
            model="m",
            provider="mock",
            input_tokens=200,
            output_tokens=150,
            cost_usd=0.005,
            latency_ms=600,
            finish_reason="stop",
        )

        mock_provider.generate.side_effect = [
            gen_response,
            critic_response,
            revision_response,
        ]

        config = LLMConfig()
        config.features.use_critic = True

        result = await generate_with_quality(
            AssetType.AGENT,
            "test",
            python_profile,
            mock_provider,
            config,
        )

        assert result.critic is not None
        assert result.critic.score == 5
        assert result.revision_response is not None
        assert result.total_cost_usd == pytest.approx(0.009)
        # 3 calls: generate, critic, revision
        assert mock_provider.generate.call_count == 3
