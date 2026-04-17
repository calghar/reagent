from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from agentguard.core.parsers import AssetType
from agentguard.evaluation.evaluator import AssetMetrics, QualityLabel, QualityReport
from agentguard.llm.instincts import (
    Instinct,
    InstinctStore,
    TelemetryContext,
    TrustTier,
    build_telemetry_context,
    ensure_bundled,
    evolve_instincts,
    export_instincts,
    extract_from_profile,
    extract_instincts,
    format_instincts_for_prompt,
    import_instincts,
    load_bundled_instincts,
    prune_stale,
    relevance_score,
)
from agentguard.telemetry.events import (
    CorrectionEvent,
    ParsedSession,
    SessionMetrics,
    ToolCall,
)
from agentguard.telemetry.profiler import (
    CorrectionHotspot,
    Workflow,
    WorkflowProfile,
)


@pytest.fixture()
def sample_instinct() -> Instinct:
    return Instinct(
        instinct_id="test-001",
        content="Use Read and Grep before editing files",
        category="agent",
        trust_tier=TrustTier.MANAGED,
        confidence=0.8,
        source="telemetry",
        last_used=datetime.now(UTC),
        use_count=3,
        success_rate=0.7,
    )


@pytest.fixture()
def store_path(tmp_path: Path) -> Path:
    return tmp_path / "instincts.json"


@pytest.fixture()
def populated_store(store_path: Path) -> InstinctStore:
    store = InstinctStore(store_path)
    store.load()
    instincts = [
        Instinct(
            instinct_id="i1",
            content="Agent tool selection best practice",
            category="agent",
            trust_tier=TrustTier.BUNDLED,
            confidence=1.0,
            source="agentguard-curated",
        ),
        Instinct(
            instinct_id="i2",
            content="Skill body structure pattern",
            category="skill",
            trust_tier=TrustTier.MANAGED,
            confidence=0.75,
            source="telemetry",
            last_used=datetime.now(UTC) - timedelta(days=10),
            use_count=5,
        ),
        Instinct(
            instinct_id="i3",
            content="Old stale instinct",
            category="rule",
            trust_tier=TrustTier.WORKSPACE,
            confidence=0.2,
            source="telemetry",
            created_at=datetime.now(UTC) - timedelta(days=120),
        ),
    ]
    for inst in instincts:
        store.add(inst)
    store.save()
    return store


@pytest.fixture()
def sample_sessions() -> list[ParsedSession]:
    tc = [
        ToolCall(tool_name="Read"),
        ToolCall(tool_name="Grep"),
        ToolCall(tool_name="Edit"),
        ToolCall(tool_name="Read"),
        ToolCall(tool_name="Grep"),
        ToolCall(tool_name="Edit"),
    ]
    corrections = [
        CorrectionEvent(
            file_path="src/main.py",
            agent_tool_call=ToolCall(tool_name="Edit"),
            user_tool_call=ToolCall(tool_name="Edit"),
        ),
        CorrectionEvent(
            file_path="src/main.py",
            agent_tool_call=ToolCall(tool_name="Edit"),
            user_tool_call=ToolCall(tool_name="Edit"),
        ),
    ]
    return [
        ParsedSession(
            session_id="s1",
            tool_calls=tc,
            corrections=corrections,
            metrics=SessionMetrics(session_id="s1"),
        ),
        ParsedSession(
            session_id="s2",
            tool_calls=tc,
            corrections=corrections,
            metrics=SessionMetrics(session_id="s2"),
        ),
    ]


@pytest.fixture()
def sample_profile() -> WorkflowProfile:
    return WorkflowProfile(
        repo_path="/test/repo",
        repo_name="repo",
        session_count=10,
        workflows=[
            Workflow(
                name="implement",
                intent="implement",
                frequency=5.0,
                typical_sequence=["Read", "Edit", "Bash"],
            ),
        ],
        coverage_gaps=["review", "debug"],
        correction_hotspots=[
            CorrectionHotspot(
                file_pattern="src/auth.py",
                correction_rate=0.35,
                correction_count=7,
            )
        ],
        tool_frequency={"Read": 50, "Edit": 30, "Bash": 20},
    )


@pytest.fixture()
def good_quality_report() -> QualityReport:
    return QualityReport(
        repo_path="/test/repo",
        repo_name="repo",
        evaluated=2,
        healthy=2,
        asset_metrics=[
            AssetMetrics(
                asset_id="a1",
                quality_score=85,
                label=QualityLabel.EXCELLENT,
            ),
            AssetMetrics(
                asset_id="a2",
                quality_score=75,
                label=QualityLabel.GOOD,
            ),
        ],
    )


@pytest.fixture()
def poor_quality_report() -> QualityReport:
    return QualityReport(
        repo_path="/test/repo",
        repo_name="repo",
        evaluated=2,
        underperforming=2,
        asset_metrics=[
            AssetMetrics(
                asset_id="a1",
                quality_score=25,
                label=QualityLabel.POOR,
            ),
            AssetMetrics(
                asset_id="a2",
                quality_score=30,
                label=QualityLabel.POOR,
            ),
        ],
    )


class TestInstinctModel:
    def test_create_instinct(self, sample_instinct: Instinct) -> None:
        assert sample_instinct.instinct_id == "test-001"
        assert sample_instinct.confidence == pytest.approx(0.8)
        assert sample_instinct.trust_tier == TrustTier.MANAGED

    def test_trust_tier_enum(self) -> None:
        assert TrustTier.BUNDLED.value == "bundled"
        assert TrustTier.MANAGED.value == "managed"
        assert TrustTier.WORKSPACE.value == "workspace"

    def test_serialization_roundtrip(self, sample_instinct: Instinct) -> None:
        data = sample_instinct.model_dump(mode="json")
        restored = Instinct.model_validate(data)
        assert restored.instinct_id == sample_instinct.instinct_id
        assert restored.confidence == sample_instinct.confidence


class TestRelevanceScoring:
    def test_category_match_boosts_score(self) -> None:
        inst = Instinct(
            instinct_id="r1",
            content="Agent tool tip",
            category="agent",
            trust_tier=TrustTier.BUNDLED,
            confidence=0.8,
            source="curated",
        )
        agent_score = relevance_score(inst, AssetType.AGENT, "test-agent")
        skill_score = relevance_score(inst, AssetType.SKILL, "test-skill")
        assert agent_score > skill_score

    def test_bundled_outscores_workspace(self) -> None:
        bundled = Instinct(
            instinct_id="b1",
            content="Some pattern",
            category="agent",
            source="test",
            confidence=0.8,
            trust_tier=TrustTier.BUNDLED,
        )
        workspace = Instinct(
            instinct_id="w1",
            content="Some pattern",
            category="agent",
            source="test",
            confidence=0.8,
            trust_tier=TrustTier.WORKSPACE,
        )
        b_score = relevance_score(bundled, AssetType.AGENT, "x")
        w_score = relevance_score(workspace, AssetType.AGENT, "x")
        assert b_score > w_score

    def test_recency_boost(self) -> None:
        recent = Instinct(
            instinct_id="r1",
            content="Recent pattern",
            category="agent",
            trust_tier=TrustTier.MANAGED,
            confidence=0.7,
            source="test",
            last_used=datetime.now(UTC),
        )
        old = Instinct(
            instinct_id="r2",
            content="Old pattern",
            category="agent",
            trust_tier=TrustTier.MANAGED,
            confidence=0.7,
            source="test",
            last_used=datetime.now(UTC) - timedelta(days=150),
        )
        assert relevance_score(recent, AssetType.AGENT, "x") > relevance_score(
            old, AssetType.AGENT, "x"
        )

    def test_score_capped_at_one(self) -> None:
        inst = Instinct(
            instinct_id="cap",
            content="test agent pattern",
            category="agent",
            trust_tier=TrustTier.BUNDLED,
            confidence=1.0,
            source="test",
            last_used=datetime.now(UTC),
        )
        score = relevance_score(inst, AssetType.AGENT, "test")
        assert score <= 1.0


class TestInstinctStore:
    def test_save_and_load(self, store_path: Path) -> None:
        store = InstinctStore(store_path)
        store.load()
        inst = Instinct(
            instinct_id="s1",
            content="Test pattern",
            category="agent",
            trust_tier=TrustTier.WORKSPACE,
            confidence=0.6,
            source="test",
        )
        store.add(inst)
        store.save()

        store2 = InstinctStore(store_path)
        store2.load()
        assert len(store2.instincts) == 1
        assert store2.instincts[0].instinct_id == "s1"

    def test_deduplication_on_add(self, store_path: Path) -> None:
        store = InstinctStore(store_path)
        store.load()
        inst = Instinct(
            instinct_id="d1",
            content="Duplicate content",
            category="agent",
            trust_tier=TrustTier.WORKSPACE,
            confidence=0.5,
            source="test",
        )
        store.add(inst)
        # Add same content again
        inst2 = Instinct(
            instinct_id="d2",
            content="Duplicate content",
            category="agent",
            trust_tier=TrustTier.WORKSPACE,
            confidence=0.5,
            source="test",
        )
        store.add(inst2)
        assert len(store.instincts) == 1
        # Confidence should increase
        assert store.instincts[0].confidence == pytest.approx(0.6)

    def test_get_relevant(self, populated_store: InstinctStore) -> None:
        relevant = populated_store.get_relevant(AssetType.AGENT, "test-agent", top_k=2)
        assert len(relevant) <= 2
        # Bundled agent instinct should rank high
        assert any(i.instinct_id == "i1" for i in relevant)

    def test_mark_used(self, populated_store: InstinctStore) -> None:
        populated_store.mark_used("i2")
        inst = next(i for i in populated_store.instincts if i.instinct_id == "i2")
        assert inst.use_count == 6  # was 5
        assert inst.last_used is not None

    def test_load_empty(self, store_path: Path) -> None:
        store = InstinctStore(store_path)
        store.load()
        assert store.instincts == []


class TestExtraction:
    def test_extract_from_sessions(self, sample_sessions: list[ParsedSession]) -> None:
        instincts = extract_instincts(sample_sessions)
        assert len(instincts) > 0
        # Should find the Read → Grep → Edit pattern
        tool_instincts = [i for i in instincts if "tool sequence" in i.content.lower()]
        assert len(tool_instincts) >= 1

    def test_extract_correction_patterns(
        self, sample_sessions: list[ParsedSession]
    ) -> None:
        instincts = extract_instincts(sample_sessions)
        correction_instincts = [
            i for i in instincts if "correction" in i.content.lower()
        ]
        assert len(correction_instincts) >= 1

    def test_extract_from_empty_sessions(self) -> None:
        assert extract_instincts([]) == []

    def test_extract_from_profile(self, sample_profile: WorkflowProfile) -> None:
        instincts = extract_from_profile(sample_profile)
        assert len(instincts) > 0
        categories = {i.category for i in instincts}
        # Should have coverage gap instincts (skill) and
        # hotspot instincts (rule) and workflow instincts (generation)
        assert "skill" in categories
        assert "rule" in categories


class TestEvolution:
    def test_good_eval_boosts_confidence(
        self, good_quality_report: QualityReport
    ) -> None:
        instincts = [
            Instinct(
                instinct_id="e1",
                content="Test",
                category="agent",
                trust_tier=TrustTier.WORKSPACE,
                confidence=0.5,
                source="test",
            )
        ]
        result = evolve_instincts(instincts, good_quality_report)
        assert result[0].confidence > 0.5

    def test_poor_eval_reduces_confidence(
        self, poor_quality_report: QualityReport
    ) -> None:
        instincts = [
            Instinct(
                instinct_id="e2",
                content="Test",
                category="agent",
                trust_tier=TrustTier.WORKSPACE,
                confidence=0.5,
                source="test",
            )
        ]
        result = evolve_instincts(instincts, poor_quality_report)
        assert result[0].confidence < 0.5

    def test_promotion_to_managed(self, good_quality_report: QualityReport) -> None:
        instincts = [
            Instinct(
                instinct_id="e3",
                content="High confidence workspace",
                category="agent",
                trust_tier=TrustTier.WORKSPACE,
                confidence=0.78,
                source="test",
                use_count=5,
            )
        ]
        result = evolve_instincts(instincts, good_quality_report)
        # After boost, confidence >= 0.8 with use_count >= 5
        assert result[0].trust_tier == TrustTier.MANAGED


class TestPruning:
    def test_prune_stale_instincts(self, populated_store: InstinctStore) -> None:
        removed = prune_stale(populated_store)
        assert removed >= 1
        # Bundled should survive
        assert any(i.instinct_id == "i1" for i in populated_store.instincts)
        # Old low-confidence instinct should be gone
        assert not any(i.instinct_id == "i3" for i in populated_store.instincts)

    def test_prune_bundled_survives(self, populated_store: InstinctStore) -> None:
        prune_stale(populated_store, max_age_days=0, min_confidence=1.0)
        bundled = [
            i for i in populated_store.instincts if i.trust_tier == TrustTier.BUNDLED
        ]
        assert len(bundled) >= 1

    def test_prune_with_custom_thresholds(self, populated_store: InstinctStore) -> None:
        # Very lenient pruning — should remove nothing except the old one
        removed = prune_stale(populated_store, max_age_days=200, min_confidence=0.1)
        # i3 is 120 days old, within 200-day window, but confidence 0.2 >= 0.1
        assert removed == 0


class TestImportExport:
    def test_export_and_import(self, tmp_path: Path) -> None:
        store = InstinctStore(tmp_path / "source.json")
        store.load()
        store.add(
            Instinct(
                instinct_id="x1",
                content="Exportable pattern",
                category="agent",
                trust_tier=TrustTier.MANAGED,
                confidence=0.9,
                source="test",
            )
        )
        store.add(
            Instinct(
                instinct_id="x2",
                content="Low confidence",
                category="agent",
                trust_tier=TrustTier.WORKSPACE,
                confidence=0.3,
                source="test",
            )
        )

        export_path = tmp_path / "exported.json"
        exported = export_instincts(store, export_path, min_confidence=0.7)
        assert exported == 1

        # Import into fresh store
        target_store = InstinctStore(tmp_path / "target.json")
        target_store.load()
        imported = import_instincts(target_store, export_path)
        assert imported == 1
        # Imported instincts reset to WORKSPACE tier
        assert target_store.instincts[0].trust_tier == TrustTier.WORKSPACE


class TestBundledInstincts:
    def test_load_bundled(self) -> None:
        instincts = load_bundled_instincts()
        assert len(instincts) >= 10
        # All should be BUNDLED tier
        assert all(i.trust_tier == TrustTier.BUNDLED for i in instincts)
        # All should have confidence 0.9+
        assert all(i.confidence >= 0.9 for i in instincts)

    def test_ensure_bundled(self, store_path: Path) -> None:
        store = InstinctStore(store_path)
        store.load()
        added = ensure_bundled(store)
        assert added >= 10
        # Second run should add nothing
        added2 = ensure_bundled(store)
        assert added2 == 0


class TestTelemetryContext:
    def test_build_from_profile(self, sample_profile: WorkflowProfile) -> None:
        ctx = build_telemetry_context(sample_profile)
        assert ctx is not None
        assert "review" in ctx.coverage_gaps
        assert ctx.tool_frequency["Read"] == 50

    def test_empty_profile_returns_none(self) -> None:
        profile = WorkflowProfile(
            repo_path="/test",
            repo_name="test",
            session_count=0,
        )
        assert build_telemetry_context(profile) is None

    def test_to_prompt_section(self) -> None:
        ctx = TelemetryContext(
            coverage_gaps=["review"],
            top_workflows=["implement"],
            tool_frequency={"Read": 10},
        )
        section = ctx.to_prompt_section()
        assert "review" in section
        assert "implement" in section
        assert "Read" in section

    def test_format_instincts_for_prompt(self) -> None:
        instincts = [
            Instinct(
                instinct_id="p1",
                content="Test instinct content",
                category="agent",
                trust_tier=TrustTier.BUNDLED,
                confidence=0.9,
                source="test",
            )
        ]
        text = format_instincts_for_prompt(instincts)
        assert "Learned Patterns" in text
        assert "bundled" in text
        assert "Test instinct content" in text

    def test_format_empty_instincts(self) -> None:
        assert format_instincts_for_prompt([]) == ""


class TestSuggestApply:
    def test_apply_dry_run(self, tmp_path: Path) -> None:
        """Dry run does not write files."""
        _ = tmp_path
        from agentguard.evaluation.suggest import ApplyResult

        result = ApplyResult(applied=2, skipped=1, paths=["a", "b"])
        assert result.applied == 2
        assert result.skipped == 1

    def test_apply_creates_files(self, tmp_path: Path) -> None:
        """apply_suggestions creates files from draft content."""
        from unittest.mock import patch

        from agentguard.evaluation.suggest import (
            Suggestion,
            SuggestionReport,
            apply_suggestions,
        )

        mock_report = SuggestionReport(
            repo_path=str(tmp_path),
            repo_name="test",
            suggestions=[
                Suggestion(
                    number=1,
                    category="uncovered-workflow",
                    title="Test",
                    description="Test suggestion",
                    draft_content="# Test skill\n",
                    target_path=".claude/skills/test/SKILL.md",
                    asset_type="skill",
                ),
            ],
        )

        with patch(
            "agentguard.evaluation.suggest.suggest_for_repo",
            return_value=mock_report,
        ):
            result = apply_suggestions(tmp_path)

        assert result.applied == 1
        target = tmp_path / ".claude" / "skills" / "test" / "SKILL.md"
        assert target.exists()
        assert target.read_text() == "# Test skill\n"

    def test_apply_skips_no_draft(self, tmp_path: Path) -> None:
        from unittest.mock import patch

        from agentguard.evaluation.suggest import (
            Suggestion,
            SuggestionReport,
            apply_suggestions,
        )

        mock_report = SuggestionReport(
            repo_path=str(tmp_path),
            repo_name="test",
            suggestions=[
                Suggestion(
                    number=1,
                    category="missing-hook",
                    title="No draft",
                    description="Cannot auto-apply",
                ),
            ],
        )

        with patch(
            "agentguard.evaluation.suggest.suggest_for_repo",
            return_value=mock_report,
        ):
            result = apply_suggestions(tmp_path)

        assert result.applied == 0
        assert result.skipped == 1
