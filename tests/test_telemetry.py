from pathlib import Path

from reagent.telemetry.events import parse_session

FIXTURES = Path(__file__).parent / "fixtures" / "transcripts"


class TestParseSession:
    def test_parse_implement_session(self) -> None:
        session = parse_session(FIXTURES / "session-implement.jsonl")

        assert session.session_id == "session-implement"
        assert session.repo_path == "/Users/dev/myproject"
        assert session.metrics.tool_count > 0
        assert session.metrics.turn_count >= 2

    def test_parse_review_session(self) -> None:
        session = parse_session(FIXTURES / "session-review.jsonl")

        assert session.session_id == "session-review"
        assert session.metrics.tool_count == 4  # 4 Read/Grep calls
        assert session.metrics.turn_count == 1

    def test_parse_release_session(self) -> None:
        session = parse_session(FIXTURES / "session-release.jsonl")

        assert session.session_id == "session-release"
        tools = [tc.tool_name for tc in session.tool_calls]
        assert all(t == "Bash" for t in tools)

    def test_extracts_tool_calls(self) -> None:
        session = parse_session(FIXTURES / "session-implement.jsonl")

        tool_names = [tc.tool_name for tc in session.tool_calls]
        assert "Read" in tool_names
        assert "Edit" in tool_names
        assert "Bash" in tool_names

    def test_extracts_messages(self) -> None:
        session = parse_session(FIXTURES / "session-implement.jsonl")

        user_msgs = [m for m in session.messages if m.role == "user"]
        asst_msgs = [m for m in session.messages if m.role == "assistant"]
        assert len(user_msgs) >= 2
        assert len(asst_msgs) >= 1

    def test_computes_tool_counts(self) -> None:
        session = parse_session(FIXTURES / "session-implement.jsonl")

        assert session.metrics.tool_counts.get("Read", 0) > 0
        assert session.metrics.tool_counts.get("Edit", 0) > 0

    def test_computes_duration(self) -> None:
        session = parse_session(FIXTURES / "session-implement.jsonl")

        assert session.metrics.duration_seconds > 0
        assert session.metrics.start_time is not None
        assert session.metrics.end_time is not None

    def test_segments_task_blocks(self) -> None:
        session = parse_session(FIXTURES / "session-implement.jsonl")

        # Should have multiple task blocks (split on user messages)
        assert len(session.task_blocks) >= 1
        for block in session.task_blocks:
            assert len(block.tool_calls) > 0

    def test_detects_corrections(self) -> None:
        session = parse_session(FIXTURES / "session-implement.jsonl")

        # The fixture has a user edit after agent edit on same file
        assert session.metrics.correction_count >= 1
        assert len(session.corrections) >= 1
        assert session.corrections[0].file_path == "src/auth.py"

    def test_handles_empty_file(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty.jsonl"
        empty.write_text("")
        session = parse_session(empty)
        assert session.metrics.tool_count == 0

    def test_handles_malformed_json(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.jsonl"
        bad.write_text("not json\n{}\n{invalid\n")
        session = parse_session(bad)
        assert session.metrics.tool_count == 0

    def test_tool_output_truncated(self) -> None:
        session = parse_session(FIXTURES / "session-implement.jsonl")
        for tc in session.tool_calls:
            assert len(tc.tool_output) <= 500

    def test_extracts_cwd_as_repo_path(self) -> None:
        session = parse_session(FIXTURES / "session-implement.jsonl")
        assert session.repo_path == "/Users/dev/myproject"
