from pathlib import Path

import yaml

from agentguard.telemetry.events import TaskBlock, ToolCall, parse_session
from agentguard.telemetry.profiler import (
    Workflow,
    WorkflowProfile,
    _extract_workflows,
    _normalize_tool_name,
    classify_intent,
    save_workflow_model,
)

FIXTURES = Path(__file__).parent / "fixtures" / "transcripts"


class TestNormalizeToolName:
    def test_read_tools(self) -> None:
        assert _normalize_tool_name("Read") == "Read"
        assert _normalize_tool_name("Glob") == "Read"
        assert _normalize_tool_name("Grep") == "Read"
        assert _normalize_tool_name("read_file") == "Read"

    def test_edit_tools(self) -> None:
        assert _normalize_tool_name("Edit") == "Edit"
        assert _normalize_tool_name("MultiEdit") == "Edit"
        assert _normalize_tool_name("edit_file") == "Edit"

    def test_write_tools(self) -> None:
        assert _normalize_tool_name("Write") == "Write"
        assert _normalize_tool_name("write_file") == "Write"

    def test_bash_tools(self) -> None:
        assert _normalize_tool_name("Bash") == "Bash"

    def test_unknown_passes_through(self) -> None:
        assert _normalize_tool_name("WebFetch") == "WebFetch"


class TestClassifyIntent:
    def _make_block(self, tool_names: list[str], **kwargs: str) -> TaskBlock:
        """Create a TaskBlock with tools for testing."""
        return TaskBlock(
            tool_calls=[
                ToolCall(tool_name=name, tool_input=kwargs) for name in tool_names
            ]
        )

    def test_implement_pattern(self) -> None:
        block = self._make_block(["Read", "Grep", "Edit", "Bash"])
        assert classify_intent(block) in ("implement", "debug")

    def test_review_pattern(self) -> None:
        block = self._make_block(["Read", "Read", "Grep", "Read"])
        assert classify_intent(block) == "review"

    def test_release_pattern(self) -> None:
        block = TaskBlock(
            tool_calls=[
                ToolCall(
                    tool_name="Bash",
                    tool_input={"command": "git push origin main"},
                ),
                ToolCall(
                    tool_name="Bash",
                    tool_input={"command": "gh pr create"},
                ),
            ]
        )
        assert classify_intent(block) == "release"

    def test_test_pattern(self) -> None:
        block = TaskBlock(
            tool_calls=[
                ToolCall(
                    tool_name="Bash",
                    tool_input={"command": "pytest tests/"},
                ),
            ]
        )
        assert classify_intent(block) == "test"

    def test_empty_block(self) -> None:
        block = TaskBlock()
        assert classify_intent(block) == "unknown"

    def test_classify_from_fixture(self) -> None:
        session = parse_session(FIXTURES / "session-implement.jsonl")
        if session.task_blocks:
            intent = classify_intent(session.task_blocks[0])
            assert intent in ("implement", "debug", "test", "review", "unknown")


class TestExtractWorkflows:
    def test_extracts_from_sessions(self) -> None:
        sessions = [
            parse_session(FIXTURES / "session-implement.jsonl"),
            parse_session(FIXTURES / "session-review.jsonl"),
        ]
        workflows = _extract_workflows(sessions)
        assert len(workflows) > 0
        intents = {w.intent for w in workflows}
        assert len(intents) >= 1

    def test_workflow_has_frequency(self) -> None:
        sessions = [
            parse_session(FIXTURES / "session-implement.jsonl"),
        ]
        workflows = _extract_workflows(sessions)
        for wf in workflows:
            assert wf.frequency > 0


class TestSaveWorkflowModel:
    def test_saves_yaml(self, tmp_path: Path) -> None:
        profile = WorkflowProfile(
            repo_path="/test/repo",
            repo_name="test-repo",
            session_count=5,
            workflows=[
                Workflow(
                    name="implement",
                    intent="implement",
                    frequency=2.0,
                    avg_turns=10,
                    typical_sequence=["Read", "Edit", "Bash"],
                )
            ],
        )

        output = save_workflow_model(profile, output_dir=tmp_path)
        assert output.exists()
        assert output.suffix == ".yaml"

        data = yaml.safe_load(output.read_text())
        assert data["repo_name"] == "test-repo"
        assert data["session_count"] == 5
        assert len(data["workflows"]) == 1

    def test_sanitizes_filename(self, tmp_path: Path) -> None:
        profile = WorkflowProfile(
            repo_path="/test/my repo!",
            repo_name="my repo!",
        )
        output = save_workflow_model(profile, output_dir=tmp_path)
        assert "!" not in output.name
        assert " " not in output.name
