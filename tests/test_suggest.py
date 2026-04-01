from unittest.mock import MagicMock

from reagent.creation.suggest import generate_suggestions
from reagent.telemetry.profiler import CorrectionHotspot, Workflow, WorkflowProfile


class TestGenerateSuggestions:
    def test_no_suggestions_for_complete_profile(self) -> None:
        profile = WorkflowProfile(
            repo_path="/test/repo",
            repo_name="repo",
            session_count=10,
            workflows=[
                Workflow(name=i, intent=i, frequency=1.0)
                for i in ("implement", "review", "debug", "test", "docs")
            ],
        )
        report = generate_suggestions(profile)
        # May still have some suggestions, but no coverage gaps
        gap_suggestions = [
            s for s in report.suggestions if s.category == "uncovered-workflow"
        ]
        assert len(gap_suggestions) == 0

    def test_suggests_missing_workflows(self) -> None:
        profile = WorkflowProfile(
            repo_path="/test/repo",
            repo_name="repo",
            session_count=10,
            workflows=[Workflow(name="implement", intent="implement", frequency=1.0)],
            coverage_gaps=["review", "debug", "test", "docs"],
        )
        report = generate_suggestions(profile)
        gap_suggestions = [
            s for s in report.suggestions if s.category == "uncovered-workflow"
        ]
        assert len(gap_suggestions) >= 1

    def test_suggests_high_correction_fixes(self) -> None:
        profile = WorkflowProfile(
            repo_path="/test/repo",
            repo_name="repo",
            session_count=10,
            correction_hotspots=[
                CorrectionHotspot(
                    file_pattern="src/auth.py",
                    correction_rate=0.35,
                    correction_count=7,
                )
            ],
        )
        report = generate_suggestions(profile)
        correction_suggestions = [
            s for s in report.suggestions if s.category == "high-correction"
        ]
        assert len(correction_suggestions) >= 1
        assert "auth.py" in correction_suggestions[0].title

    def test_suggests_hooks_when_no_sessions(self) -> None:
        profile = WorkflowProfile(
            repo_path="/test/repo",
            repo_name="repo",
            session_count=0,
        )
        report = generate_suggestions(profile)
        hook_suggestions = [
            s for s in report.suggestions if s.category == "missing-hook"
        ]
        assert len(hook_suggestions) >= 1

    def test_suggestion_numbering(self) -> None:
        profile = WorkflowProfile(
            repo_path="/test/repo",
            repo_name="repo",
            session_count=0,
            coverage_gaps=["review", "debug"],
        )
        report = generate_suggestions(profile)
        numbers = [s.number for s in report.suggestions]
        assert numbers == list(range(1, len(numbers) + 1))

    def test_get_suggestion_by_number(self) -> None:
        profile = WorkflowProfile(
            repo_path="/test/repo",
            repo_name="repo",
            session_count=0,
            coverage_gaps=["review"],
        )
        report = generate_suggestions(profile)
        assert report.get_suggestion(1) is not None
        assert report.get_suggestion(999) is None

    def test_draft_content_present(self) -> None:
        profile = WorkflowProfile(
            repo_path="/test/repo",
            repo_name="repo",
            session_count=10,
            correction_hotspots=[
                CorrectionHotspot(
                    file_pattern="src/models.py",
                    correction_rate=0.25,
                    correction_count=5,
                )
            ],
            coverage_gaps=["debug"],
        )
        report = generate_suggestions(profile)
        for s in report.suggestions:
            if s.category in ("high-correction", "uncovered-workflow"):
                assert s.draft_content, f"Suggestion {s.number} has no draft"

    def test_dedup_skips_gaps_covered_by_catalog(self) -> None:
        """Coverage gaps already in the catalog should not produce suggestions."""

        profile = WorkflowProfile(
            repo_path="/test/repo",
            repo_name="repo",
            session_count=5,
            coverage_gaps=["debug", "review"],
        )
        # Mock a catalog whose all_entries() returns an entry named "debug"
        mock_catalog = MagicMock()
        entry = MagicMock()
        entry.name = "debug"
        mock_catalog.all_entries.return_value = [entry]

        report = generate_suggestions(profile, mock_catalog)
        gap_suggestions = [
            s for s in report.suggestions if s.category == "uncovered-workflow"
        ]
        # "debug" should be skipped; "review" should still appear
        titles = [s.title for s in gap_suggestions]
        assert all("debug" not in t for t in titles), (
            "Expected 'debug' gap to be deduped by catalog"
        )
        assert any("review" in t for t in titles), (
            "Expected 'review' gap to still produce a suggestion"
        )

    def test_dedup_no_catalog_suggests_all_gaps(self) -> None:
        """Without a catalog all coverage gaps produce suggestions."""
        profile = WorkflowProfile(
            repo_path="/test/repo",
            repo_name="repo",
            session_count=5,
            coverage_gaps=["debug", "review"],
        )
        report = generate_suggestions(profile, catalog=None)
        gap_suggestions = [
            s for s in report.suggestions if s.category == "uncovered-workflow"
        ]
        assert len(gap_suggestions) == 2
