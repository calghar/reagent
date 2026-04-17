import json
import logging
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from agentguard._tuning import get_tuning
from agentguard.core.parsers import AssetType
from agentguard.evaluation.evaluator import QualityReport
from agentguard.telemetry.events import ParsedSession
from agentguard.telemetry.profiler import WorkflowProfile

logger = logging.getLogger(__name__)


class TrustTier(StrEnum):
    """Trust tier for instinct provenance."""

    BUNDLED = "bundled"
    MANAGED = "managed"
    WORKSPACE = "workspace"


class Instinct(BaseModel):
    """A learned pattern extracted from session analysis."""

    instinct_id: str
    content: str
    category: str  # "generation", "evaluation", "security", etc.
    trust_tier: TrustTier
    confidence: float  # 0.0 - 1.0
    source: str  # Where it was learned from
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_used: datetime | None = None
    use_count: int = 0
    success_rate: float = 0.0
    ttl_days: int = 90


def relevance_score(instinct: Instinct, asset_type: AssetType, name: str) -> float:
    """Score instinct relevance to a generation task.

    Higher scores mean the instinct is more relevant.

    Args:
        instinct: The instinct to score.
        asset_type: Target asset type being generated.
        name: Name of the asset being generated.

    Returns:
        Relevance score in [0.0, 1.0].
    """
    score = instinct.confidence

    # Category match boost
    if instinct.category == asset_type.value:
        score *= get_tuning().instinct.category_match_boost

    # Recency boost
    if instinct.last_used:
        days_ago = (datetime.now(UTC) - instinct.last_used).days
        score *= max(0.5, 1.0 - days_ago / get_tuning().instinct.recency_half_life_days)

    # Trust tier weight
    tier_weights = {
        TrustTier.BUNDLED: 1.0,
        TrustTier.MANAGED: get_tuning().instinct.trust_tier_weights["managed"],
        TrustTier.WORKSPACE: get_tuning().instinct.trust_tier_weights["workspace"],
    }
    score *= tier_weights[instinct.trust_tier]

    # Name word overlap
    name_words = set(name.replace("-", " ").lower().split())
    content_words = set(instinct.content.lower().split()[:20])
    if name_words and content_words:
        overlap = len(name_words & content_words)
        score *= 1.0 + overlap * get_tuning().instinct.name_overlap_factor

    return min(score, 1.0)


class InstinctStore:
    """Instinct store with SQLite primary storage and JSON fallback.

    When a ``sqlite3.Connection`` is provided, instincts are persisted
    in the ``instincts`` table with FTS5 search support.  Otherwise
    falls back to reading/writing a single JSON file.
    """

    def __init__(
        self,
        path: Path,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        self.path = path
        self._instincts: list[Instinct] = []
        self._db = connection

    def load(self) -> None:
        """Load instincts from SQLite or JSON file."""
        if self._db is not None:
            self._load_sqlite()
        else:
            self._load_json()

    def _load_json(self) -> None:
        if not self.path.exists():
            self._instincts = []
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self._instincts = [Instinct.model_validate(d) for d in data]

    def _load_sqlite(self) -> None:
        if self._db is None:
            raise RuntimeError(
                "No SQLite connection available; call load()\
                 with a connection for SQLite persistence"
            )
        cursor = self._db.execute(
            "SELECT instinct_id, content, category, trust_tier, confidence, "
            "source, created_at, last_used, use_count, success_rate, ttl_days "
            "FROM instincts"
        )
        self._instincts = []
        for row in cursor.fetchall():
            self._instincts.append(
                Instinct(
                    instinct_id=row[0],
                    content=row[1],
                    category=row[2],
                    trust_tier=TrustTier(row[3]),
                    confidence=row[4],
                    source=row[5],
                    created_at=datetime.fromisoformat(row[6]),
                    last_used=(datetime.fromisoformat(row[7]) if row[7] else None),
                    use_count=row[8],
                    success_rate=row[9],
                    ttl_days=row[10],
                )
            )

    def save(self) -> None:
        """Persist instincts to SQLite or JSON file."""
        if self._db is not None:
            self._save_sqlite()
        else:
            self._save_json()

    def _save_json(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = [inst.model_dump(mode="json") for inst in self._instincts]
        self.path.write_text(
            json.dumps(data, indent=2, default=str),
            encoding="utf-8",
        )

    def _save_sqlite(self) -> None:
        if self._db is None:
            raise RuntimeError(
                "No SQLite connection available; call save()\
                 with a connection for SQLite persistence"
            )
        for inst in self._instincts:
            self._db.execute(
                """INSERT OR REPLACE INTO instincts
                   (instinct_id, content, category, trust_tier, confidence,
                    source, created_at, last_used, use_count, success_rate,
                    ttl_days)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    inst.instinct_id,
                    inst.content,
                    inst.category,
                    inst.trust_tier.value,
                    inst.confidence,
                    inst.source,
                    inst.created_at.isoformat(),
                    inst.last_used.isoformat() if inst.last_used else None,
                    inst.use_count,
                    inst.success_rate,
                    inst.ttl_days,
                ),
            )
        self._db.commit()

    @property
    def instincts(self) -> list[Instinct]:
        return list(self._instincts)

    def add(self, instinct: Instinct) -> None:
        """Add an instinct, deduplicating by content."""
        for existing in self._instincts:
            if existing.content == instinct.content:
                existing.confidence = min(
                    1.0,
                    existing.confidence + get_tuning().instinct.confidence_increment,
                )
                existing.use_count += 1
                return
        self._instincts.append(instinct)

    def search_fts(self, query: str, limit: int = 10) -> list[Instinct]:
        """Full-text search using FTS5 (SQLite only).

        Falls back to substring matching when no database connection.
        """
        if self._db is not None:
            return self._search_fts_sqlite(query, limit)
        # Fallback: simple substring match
        query_lower = query.lower()
        matches = [
            inst
            for inst in self._instincts
            if query_lower in inst.content.lower()
            or query_lower in inst.category.lower()
        ]
        return matches[:limit]

    def _search_fts_sqlite(
        self,
        query: str,
        limit: int,
    ) -> list[Instinct]:
        if self._db is None:
            raise RuntimeError(
                "No SQLite connection available; call load()\
                 with a connection for SQLite persistence"
            )
        cursor = self._db.execute(
            "SELECT i.instinct_id, i.content, i.category, i.trust_tier, "
            "i.confidence, i.source, i.created_at, i.last_used, "
            "i.use_count, i.success_rate, i.ttl_days "
            "FROM instincts_fts f "
            "JOIN instincts i ON f.rowid = i.id "
            "WHERE instincts_fts MATCH ? "
            "LIMIT ?",
            (query, limit),
        )
        results: list[Instinct] = []
        for row in cursor.fetchall():
            results.append(
                Instinct(
                    instinct_id=row[0],
                    content=row[1],
                    category=row[2],
                    trust_tier=TrustTier(row[3]),
                    confidence=row[4],
                    source=row[5],
                    created_at=datetime.fromisoformat(row[6]),
                    last_used=(datetime.fromisoformat(row[7]) if row[7] else None),
                    use_count=row[8],
                    success_rate=row[9],
                    ttl_days=row[10],
                )
            )
        return results

    def get_relevant(
        self,
        asset_type: AssetType,
        name: str,
        top_k: int | None = None,
    ) -> list[Instinct]:
        """Find instincts most relevant to a generation task.

        Args:
            asset_type: Target asset type.
            name: Asset name.
            top_k: Maximum instincts to return.

        Returns:
            Top-k instincts sorted by relevance.
        """
        effective_k = (
            top_k if top_k is not None else get_tuning().instinct.default_top_k
        )
        scored = [
            (inst, relevance_score(inst, asset_type, name)) for inst in self._instincts
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [inst for inst, _ in scored[:effective_k]]

    def mark_used(self, instinct_id: str) -> None:
        """Record that an instinct was used in generation."""
        for inst in self._instincts:
            if inst.instinct_id == instinct_id:
                inst.last_used = datetime.now(UTC)
                inst.use_count += 1
                break


def _generate_id() -> str:
    return uuid.uuid4().hex[:12]


def extract_instincts(sessions: list[ParsedSession]) -> list[Instinct]:
    """Extract instincts from telemetry sessions.

    Looks for recurring patterns: repeated tool sequences, correction
    hotspots, and workflow patterns that appear across sessions.

    Args:
        sessions: Parsed session transcripts.

    Returns:
        List of newly extracted instincts.
    """
    if not sessions:
        return []

    instincts: list[Instinct] = []

    # Pattern 1: Frequent tool sequences (workflow instincts)
    from collections import Counter

    seq_counter: Counter[str] = Counter()
    for session in sessions:
        tools = [tc.tool_name for tc in session.tool_calls]
        for i in range(len(tools) - 2):
            seq = " → ".join(tools[i : i + 3])
            seq_counter[seq] += 1

    for seq, count in seq_counter.most_common(5):
        if count < 2:
            break
        instincts.append(
            Instinct(
                instinct_id=_generate_id(),
                content=f"Common tool sequence: {seq}",
                category="generation",
                trust_tier=TrustTier.WORKSPACE,
                confidence=min(count / 10, 0.9),
                source="telemetry",
            )
        )

    # Pattern 2: High-correction files → rules instincts
    from collections import defaultdict

    file_corrections: dict[str, int] = defaultdict(int)
    for session in sessions:
        for correction in session.corrections:
            file_corrections[correction.file_path] += 1

    for file_path, count in sorted(file_corrections.items(), key=lambda x: -x[1])[:3]:
        if count < 2:
            continue
        instincts.append(
            Instinct(
                instinct_id=_generate_id(),
                content=(
                    f"File '{file_path}' has high correction rate "
                    f"({count} corrections). Consider adding targeted rules."
                ),
                category="rule",
                trust_tier=TrustTier.WORKSPACE,
                confidence=min(
                    count / get_tuning().instinct.confidence_divisor,
                    get_tuning().instinct.confidence_cap,
                ),
                source="telemetry",
            )
        )

    return instincts


def extract_from_profile(profile: WorkflowProfile) -> list[Instinct]:
    """Extract instincts from a workflow profile.

    Args:
        profile: Workflow profile from telemetry analysis.

    Returns:
        List of new instincts derived from profile.
    """
    instincts: list[Instinct] = []

    # Coverage gaps → skill instincts
    for gap in profile.coverage_gaps:
        instincts.append(
            Instinct(
                instinct_id=_generate_id(),
                content=f"Coverage gap: no skill covers the '{gap}' workflow.",
                category="skill",
                trust_tier=TrustTier.WORKSPACE,
                confidence=0.6,
                source="telemetry",
            )
        )

    # High-correction hotspots → rule instincts
    for hotspot in profile.correction_hotspots:
        if hotspot.correction_rate < get_tuning().instinct.correction_rate_threshold:
            continue
        instincts.append(
            Instinct(
                instinct_id=_generate_id(),
                content=(
                    f"High correction rate ({hotspot.correction_rate:.0%}) "
                    f"on {hotspot.file_pattern}. Add targeted coding rules."
                ),
                category="rule",
                trust_tier=TrustTier.WORKSPACE,
                confidence=min(hotspot.correction_rate * 2, 0.9),
                source="telemetry",
            )
        )

    # Workflow patterns → generation instincts
    for wf in profile.workflows:
        if wf.frequency >= 3:
            instincts.append(
                Instinct(
                    instinct_id=_generate_id(),
                    content=(
                        f"Recurring '{wf.intent}' workflow "
                        f"({wf.frequency:.1f}/session): "
                        f"{' → '.join(wf.typical_sequence[:5])}"
                    ),
                    category="generation",
                    trust_tier=TrustTier.WORKSPACE,
                    confidence=min(wf.frequency / 10, 0.9),
                    source="telemetry",
                )
            )

    return instincts


def evolve_instincts(
    instincts: list[Instinct],
    evaluation: QualityReport,
) -> list[Instinct]:
    """Update instinct confidence based on evaluation outcomes.

    Instincts aligned with high-quality assets get confidence boosts;
    those aligned with low-quality assets get penalties.

    Args:
        instincts: Current instinct set.
        evaluation: Quality report from asset evaluation.

    Returns:
        Updated instinct list.
    """
    if not evaluation.asset_metrics:
        return instincts

    avg_score = sum(m.quality_score for m in evaluation.asset_metrics) / len(
        evaluation.asset_metrics
    )

    changed = False
    tuning = get_tuning().instinct
    for inst in instincts:
        if avg_score >= tuning.quality_score_threshold:
            # Good outcomes: small confidence boost
            inst.confidence = min(1.0, inst.confidence + tuning.confidence_reward)
            inst.success_rate = min(
                1.0, inst.success_rate + tuning.confidence_increment
            )
            changed = True
        elif avg_score < 40:
            # Poor outcomes: confidence penalty
            inst.confidence = max(0.0, inst.confidence - tuning.confidence_penalty)
            inst.success_rate = max(0.0, inst.success_rate - tuning.confidence_penalty)
            changed = True

        # Promote workspace instincts with high confidence to managed
        if (
            inst.trust_tier == TrustTier.WORKSPACE
            and inst.confidence >= tuning.confidence_cap
            and inst.use_count >= tuning.min_use_count_for_promotion
        ):
            inst.trust_tier = TrustTier.MANAGED
            changed = True

    if changed:
        logger.info(
            "Evolved %d instincts (avg score: %.1f)",
            len(instincts),
            avg_score,
        )
    return instincts


def prune_stale(
    store: InstinctStore,
    max_age_days: int = 90,
    min_confidence: float = 0.3,
) -> int:
    """Remove low-confidence or expired instincts.

    Bundled instincts are never pruned.

    Args:
        store: Instinct store to prune.
        max_age_days: Maximum age before pruning review.
        min_confidence: Minimum confidence to keep.

    Returns:
        Number of instincts removed.
    """
    cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
    before = len(store._instincts)

    store._instincts = [
        inst
        for inst in store._instincts
        if inst.trust_tier == TrustTier.BUNDLED
        or (inst.confidence >= min_confidence and inst.created_at >= cutoff)
    ]

    removed = before - len(store._instincts)
    if removed:
        logger.info("Pruned %d stale instincts", removed)
    return removed


def import_instincts(store: InstinctStore, source_path: Path) -> int:
    """Import instincts from a JSON file.

    Imported instincts are set to WORKSPACE tier regardless of source.

    Args:
        store: Target instinct store.
        source_path: Path to JSON file with instinct data.

    Returns:
        Number of instincts imported.
    """
    data = json.loads(source_path.read_text(encoding="utf-8"))
    count = 0
    for item in data:
        inst = Instinct.model_validate(item)
        inst.trust_tier = TrustTier.WORKSPACE
        store.add(inst)
        count += 1
    return count


def export_instincts(
    store: InstinctStore,
    target_path: Path,
    min_confidence: float = 0.7,
) -> int:
    """Export high-confidence instincts to a JSON file.

    Args:
        store: Source instinct store.
        target_path: Output JSON file path.
        min_confidence: Minimum confidence threshold for export.

    Returns:
        Number of instincts exported.
    """
    exportable = [inst for inst in store.instincts if inst.confidence >= min_confidence]
    target_path.parent.mkdir(parents=True, exist_ok=True)
    data = [inst.model_dump(mode="json") for inst in exportable]
    target_path.write_text(
        json.dumps(data, indent=2, default=str),
        encoding="utf-8",
    )
    return len(exportable)


_BUNDLED_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "instincts" / "bundled.json"
)


def load_bundled_instincts() -> list[Instinct]:
    """Load the curated bundled instinct set.

    Returns:
        List of bundled instincts, or empty list if file missing.
    """
    if not _BUNDLED_PATH.exists():
        logger.warning("Bundled instincts not found at %s", _BUNDLED_PATH)
        return []
    data = json.loads(_BUNDLED_PATH.read_text(encoding="utf-8"))
    return [Instinct.model_validate(d) for d in data]


def ensure_bundled(store: InstinctStore) -> int:
    """Ensure bundled instincts are present in the store.

    Adds any bundled instincts not already in the store.

    Args:
        store: Instinct store to populate.

    Returns:
        Number of bundled instincts added.
    """
    bundled = load_bundled_instincts()
    existing_ids = {inst.instinct_id for inst in store.instincts}
    added = 0
    for inst in bundled:
        if inst.instinct_id not in existing_ids:
            store._instincts.append(inst)
            added += 1
    return added


class TelemetryContext(BaseModel):
    """Telemetry summary for injection into generation prompts."""

    coverage_gaps: list[str] = Field(default_factory=list)
    top_workflows: list[str] = Field(default_factory=list)
    tool_frequency: dict[str, int] = Field(default_factory=dict)

    def to_prompt_section(self) -> str:
        """Format as a prompt section string."""
        lines: list[str] = []
        if self.coverage_gaps:
            lines.append(f"- Coverage gaps: {', '.join(self.coverage_gaps)}")
        if self.top_workflows:
            lines.append(f"- Top workflows: {', '.join(self.top_workflows)}")
        if self.tool_frequency:
            top_tools = sorted(self.tool_frequency.items(), key=lambda x: -x[1])[:5]
            freq_str = ", ".join(f"{t}({c})" for t, c in top_tools)
            lines.append(f"- Tool frequency: {freq_str}")
        return "\n".join(lines)


def build_telemetry_context(
    profile: WorkflowProfile,
) -> TelemetryContext | None:
    """Build a TelemetryContext from a workflow profile.

    Args:
        profile: Workflow profile from telemetry.

    Returns:
        TelemetryContext if data is available, None otherwise.
    """
    if profile.session_count == 0:
        return None

    return TelemetryContext(
        coverage_gaps=profile.coverage_gaps,
        top_workflows=[wf.intent for wf in profile.workflows[:5]],
        tool_frequency=profile.tool_frequency,
    )


def format_instincts_for_prompt(instincts: list[Instinct]) -> str:
    """Format a list of instincts as a prompt context section.

    Args:
        instincts: Instincts to include.

    Returns:
        Formatted string for prompt injection.
    """
    if not instincts:
        return ""

    lines = ["## Learned Patterns (instincts)"]
    for inst in instincts:
        tier_label = inst.trust_tier.value
        lines.append(
            f"- [{tier_label}] (confidence: {inst.confidence:.1f}) {inst.content}"
        )
    return "\n".join(lines)
