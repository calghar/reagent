import logging
import sqlite3
import time
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel

from reagent.intelligence.analyzer import RepoProfile, analyze_repo
from reagent.loops.guardrails import GuardrailChecker, LoopConfig
from reagent.loops.state import ApprovalQueue, ChangeRecord, LoopState, PendingAsset

logger = logging.getLogger(__name__)

_STOP_DIR = Path.home() / ".reagent"
_STOP_FILE_PREFIX = "loop_stop_"


def _clear_stop_signal() -> None:
    """Remove the loop stop sentinel file if it exists."""
    stop_file = _STOP_DIR / f"{_STOP_FILE_PREFIX}signal"
    try:
        stop_file.unlink(missing_ok=True)
    except OSError:
        pass


class LoopType(StrEnum):
    """Identifies which autonomous loop mode is running."""

    INIT = "init"
    IMPROVE = "improve"
    WATCH = "watch"


class LoopResult(BaseModel):
    """Summary produced at the end of a completed or stopped loop."""

    loop_id: str
    loop_type: str
    iterations: int
    assets_generated: int
    avg_score: float
    total_cost: float
    pending_count: int
    stop_reason: str | None = None
    status: str = "completed"


def _score_content(content: str) -> float:
    """Estimate quality score from content length and structure.

    Used when a full telemetry-backed evaluation is not yet possible
    (asset hasn't been deployed).  Scores 0-100.

    Args:
        content: Generated asset text.

    Returns:
        Heuristic quality score between 0.0 and 100.0.
    """
    if not content:
        return 0.0

    length = len(content)
    # Length component: up to 40 points for ≥500 chars
    length_score = min(length / 500.0, 1.0) * 40.0

    # Structure: frontmatter block present
    frontmatter_score = 15.0 if content.startswith("---") else 0.0

    # Has body text beyond just frontmatter
    lines = content.splitlines()
    body_lines = [ln for ln in lines if ln.strip() and not ln.startswith("---")]
    body_score = min(len(body_lines) / 10.0, 1.0) * 25.0

    # Keywords suggest purposeful content
    keywords = ("agent", "skill", "description", "tool", "usage", "example", "step")
    keyword_hits = sum(1 for kw in keywords if kw in content.lower())
    keyword_score = min(keyword_hits / len(keywords), 1.0) * 20.0

    return round(length_score + frontmatter_score + body_score + keyword_score, 1)


class QualityGateResult:
    """Result from running all quality gates against a batch of pending assets."""

    __slots__ = ("failed_assets", "passed", "reason")

    def __init__(
        self,
        passed: bool,
        reason: str | None = None,
        failed_assets: list[str] | None = None,
    ) -> None:
        self.passed = passed
        self.reason = reason
        self.failed_assets: list[str] = failed_assets or []


def _check_asset_gates(asset: PendingAsset) -> str | None:
    """Run quality gates against a single pending asset.

    Returns:
        A reason string if the asset failed a gate, or ``None`` if it passed.
    """
    # Gate 1: schema validation
    try:
        from reagent.core.parsers import _split_frontmatter
        from reagent.intelligence.schema_validator import validate_frontmatter

        fm, _ = _split_frontmatter(asset.content)
        result = validate_frontmatter(fm, asset.asset_type, asset.asset_name)
        errors = [i for i in result.issues if i.severity.value == "error"]
        if errors:
            return (
                f"Schema validation failed for {asset.asset_name}: {errors[0].message}"
            )
    except (ValueError, KeyError) as exc:
        logger.debug("Schema gate skipped for %s: %s", asset.asset_name, exc)

    # Gate 2: security scan
    try:
        from reagent.security.scanner import Severity, scan_content

        findings = scan_content(asset.content, Path(asset.file_path))
        critical_or_high = [
            f for f in findings if f.severity in (Severity.CRITICAL, Severity.HIGH)
        ]
        if critical_or_high:
            return (
                f"Security gate failed for {asset.asset_name}: "
                f"{critical_or_high[0].description}"
            )
    except (OSError, ValueError) as exc:
        logger.debug("Security gate skipped for %s: %s", asset.asset_name, exc)

    # Gate 3: regression check
    if asset.previous_score is not None and asset.new_score < asset.previous_score:
        return (
            f"Regression detected for {asset.asset_name}: "
            f"{asset.new_score:.1f} < {asset.previous_score:.1f}"
        )

    return None


def _run_quality_gates(
    pending_assets: list[PendingAsset],
    queue: ApprovalQueue | None = None,
) -> QualityGateResult:
    """Run quality gates per-asset, rejecting failures and keeping passes.

    Assets that fail a gate are marked ``status='rejected'`` in the
    approval queue (if provided) so they don't pollute the pending list.
    The loop continues as long as at least one asset passes.

    Args:
        pending_assets: The assets produced in a single iteration.
        queue: Approval queue for updating failed asset status.

    Returns:
        QualityGateResult.  ``passed=True`` if any asset survived the gates.
    """
    failed_names: list[str] = []
    reasons: list[str] = []

    for asset in pending_assets:
        reason = _check_asset_gates(asset)
        if reason:
            logger.warning("Quality gate: %s", reason)
            failed_names.append(asset.asset_name)
            reasons.append(reason)
            if queue is not None:
                try:
                    queue.reject(asset.pending_id)
                except sqlite3.Error:
                    logger.debug("Could not reject %s in queue", asset.pending_id)

    if failed_names and len(failed_names) == len(pending_assets):
        return QualityGateResult(
            passed=False,
            reason="; ".join(reasons),
            failed_assets=failed_names,
        )

    if failed_names:
        logger.info(
            "Quality gates: %d/%d assets failed, continuing with passing assets",
            len(failed_names),
            len(pending_assets),
        )

    return QualityGateResult(passed=True, failed_assets=failed_names)


def _detect_asset_plan(profile: object, max_assets: int) -> list[tuple[str, str]]:
    """Derive an (asset_type, name) plan from a repo profile.

    Args:
        profile: RepoProfile instance.
        max_assets: Maximum number of assets to plan.

    Returns:
        List of (asset_type, name) tuples.
    """
    if not isinstance(profile, RepoProfile):
        return []

    lang = (profile.primary_language or "generic").lower()
    plan: list[tuple[str, str]] = []

    plan.append(("agent", f"{lang}-dev"))
    plan.append(("agent", f"{lang}-reviewer"))
    plan.append(("skill", f"{lang}-add-feature"))

    if profile.has_ci:
        plan.append(("agent", "ci-helper"))
    if profile.has_api_routes:
        plan.append(("skill", "api-endpoint"))
    if profile.test_config and profile.test_config.runner:
        plan.append(("skill", f"{profile.test_config.runner}-tests"))

    return plan[:max_assets]


def _find_existing_assets(repo_path: Path) -> list[Path]:
    """Scan .claude/ directory for all asset files.

    Args:
        repo_path: Repository root path.

    Returns:
        List of paths to asset files found under .claude/.
    """
    claude_dir = repo_path / ".claude"
    if not claude_dir.exists():
        return []

    patterns = [
        "agents/*.md",
        "skills/*/SKILL.md",
        "commands/*.md",
        "rules/*.md",
    ]
    paths: list[Path] = []
    for pat in patterns:
        paths.extend(claude_dir.glob(pat))

    # Also check for CLAUDE.md at repo root
    claude_md = repo_path / "CLAUDE.md"
    if claude_md.exists():
        paths.append(claude_md)

    return paths


def _method_from_origin(origin: str) -> str:
    """Derive the generation method label from an AssetDraft origin string.

    Args:
        origin: The ``origin`` attribute of an ``AssetDraft``.

    Returns:
        ``"llm"`` or ``"enhanced_template"``.
    """
    if "llm" in origin or "tier1" in origin.lower():
        return "llm"
    return "enhanced_template"


def _build_pending(
    draft: object,
    loop_id: str,
    iteration: int,
    prev_content: str | None,
    prev_score: float | None,
) -> PendingAsset:
    """Construct a PendingAsset from an AssetDraft.

    Args:
        draft: AssetDraft instance from creator.
        loop_id: Owning loop ID.
        iteration: Current iteration number.
        prev_content: Previous file content, or None for new assets.
        prev_score: Previous quality score, or None for new assets.

    Returns:
        New PendingAsset ready for the queue.
    """
    from reagent.creation.creator import AssetDraft

    if not isinstance(draft, AssetDraft):
        msg = "Expected AssetDraft instance"
        raise TypeError(msg)

    score = _score_content(draft.content)
    origin = getattr(draft, "origin", "reagent-create")
    method = _method_from_origin(origin)

    return PendingAsset(
        asset_type=draft.asset_type,
        asset_name=draft.name,
        file_path=str(draft.target_path),
        content=draft.content,
        previous_content=prev_content,
        previous_score=prev_score,
        new_score=score,
        generation_method=method,
        loop_id=loop_id,
        iteration=iteration,
    )


def _save_loop_to_db(state: LoopState, db_path: Path | None) -> None:
    """Upsert the loop state row in the ``loops`` table.

    Args:
        state: Current loop state.
        db_path: Database path (None → default).
    """
    from reagent.storage import ReagentDB

    avg_score = (sum(state.scores) / len(state.scores)) if state.scores else None
    with ReagentDB(db_path) as db:
        conn = db.connect()
        conn.execute(
            """
            INSERT INTO loops (loop_id, loop_type, repo_path, status, stop_reason,
                               iteration, total_cost, avg_score, started_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(loop_id) DO UPDATE SET
                status=excluded.status,
                stop_reason=excluded.stop_reason,
                iteration=excluded.iteration,
                total_cost=excluded.total_cost,
                avg_score=excluded.avg_score
            """,
            (
                state.loop_id,
                state.loop_type,
                state.repo_path,
                state.status,
                state.stop_reason,
                state.iteration,
                state.total_cost,
                avg_score,
                state.started_at.isoformat(),
            ),
        )
        conn.commit()


def _mark_loop_complete(
    state: LoopState, stop_reason: str | None, db_path: Path | None
) -> None:
    """Mark the loop as completed in the DB.

    Args:
        state: Loop state to finalise.
        stop_reason: Reason for stopping, or None on natural completion.
        db_path: Database path (None → default).
    """
    from datetime import UTC, datetime

    from reagent.storage import ReagentDB

    now = datetime.now(UTC).isoformat()
    status = "stopped" if stop_reason else "completed"
    with ReagentDB(db_path) as db:
        conn = db.connect()
        conn.execute(
            """
            UPDATE loops
            SET status=?, stop_reason=?, completed_at=?
            WHERE loop_id=?
            """,
            (status, stop_reason, now, state.loop_id),
        )
        conn.commit()


class LoopController:
    """Orchestrates autonomous generation-evaluation-improvement loops.

    Usage::

        ctrl = LoopController()
        result = ctrl.run_init(repo_path, config)

    All three loop methods are synchronous and block until the loop
    terminates (via a guardrail, the target score, or a kill signal).
    """

    def __init__(self, db_path: Path | None = None) -> None:
        """Initialise the controller.

        Args:
            db_path: Override database path.  ``None`` uses the default.
        """
        self._kill_switch: bool = False
        self._db_path = db_path
        self._queue = ApprovalQueue(db_path)
        self._guardrails = GuardrailChecker()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def stop(self) -> None:
        """Activate the kill switch to stop any running loop.

        Also writes a sentinel file to ``~/.reagent/loop_stop_<id>``
        so that external processes can signal a stop.
        """
        self._kill_switch = True
        _STOP_DIR.mkdir(parents=True, exist_ok=True)
        (_STOP_DIR / f"{_STOP_FILE_PREFIX}signal").write_text("stop", encoding="utf-8")
        logger.info("Loop kill switch activated")

    def run_init(self, repo_path: Path, config: LoopConfig | None = None) -> LoopResult:
        """Run the init loop: generate assets from scratch.

        Analyses the repo profile, generates a set of assets, scores
        them, and iterates until the target score is reached or a
        guardrail fires.

        Args:
            repo_path: Repository root path.
            config: Loop configuration.  Defaults to ``LoopConfig()``.

        Returns:
            Summary of the loop run.
        """
        cfg = config or LoopConfig()
        repo_path = repo_path.resolve()
        self._kill_switch = False
        _clear_stop_signal()

        state = LoopState(loop_type=LoopType.INIT, repo_path=str(repo_path))
        _save_loop_to_db(state, self._db_path)

        try:
            return self._init_loop(state, repo_path, cfg)
        except Exception as exc:
            logger.exception("Init loop failed: %s", exc)
            state.status = "failed"
            state.stop_reason = str(exc)
            _save_loop_to_db(state, self._db_path)
            return _state_to_result(state, self._queue)

    def run_improve(
        self, repo_path: Path, config: LoopConfig | None = None
    ) -> LoopResult:
        """Run the improve loop: regenerate below-threshold assets.

        Finds existing assets under ``.claude/``, evaluates scores via
        content heuristics, regenerates the lowest scorers, and
        iterates until all assets exceed the target or a guardrail fires.

        Args:
            repo_path: Repository root path.
            config: Loop configuration.  Defaults to ``LoopConfig()``.

        Returns:
            Summary of the loop run.
        """
        cfg = config or LoopConfig()
        repo_path = repo_path.resolve()
        self._kill_switch = False
        _clear_stop_signal()

        state = LoopState(loop_type=LoopType.IMPROVE, repo_path=str(repo_path))
        _save_loop_to_db(state, self._db_path)

        try:
            return self._improve_loop(state, repo_path, cfg)
        except Exception as exc:
            logger.exception("Improve loop failed: %s", exc)
            state.status = "failed"
            state.stop_reason = str(exc)
            _save_loop_to_db(state, self._db_path)
            return _state_to_result(state, self._queue)

    def run_watch(
        self, repo_path: Path, config: LoopConfig | None = None
    ) -> LoopResult:
        """Run the watch loop: monitor repo for changes and regenerate.

        Polls file modification times under ``.claude/`` and regenerates
        assets that have changed since the last poll.  Runs until the
        kill switch fires or a guardrail is exceeded.

        Args:
            repo_path: Repository root path.
            config: Loop configuration.  Defaults to ``LoopConfig()``.

        Returns:
            Summary of the loop run.
        """
        cfg = config or LoopConfig()
        repo_path = repo_path.resolve()
        self._kill_switch = False
        _clear_stop_signal()

        state = LoopState(loop_type=LoopType.WATCH, repo_path=str(repo_path))
        _save_loop_to_db(state, self._db_path)

        try:
            return self._watch_loop(state, repo_path, cfg)
        except Exception as exc:
            logger.exception("Watch loop failed: %s", exc)
            state.status = "failed"
            state.stop_reason = str(exc)
            _save_loop_to_db(state, self._db_path)
            return _state_to_result(state, self._queue)

    # ------------------------------------------------------------------
    # Loop implementations (private)
    # ------------------------------------------------------------------

    def _init_loop(
        self, state: LoopState, repo_path: Path, cfg: LoopConfig
    ) -> LoopResult:
        """Execute the init loop body.

        Iteration 1 generates the full asset plan.  Subsequent iterations
        regenerate only the lowest-scoring assets from the previous round,
        targeting the weakest performers until the target score is reached.

        Args:
            state: Mutable loop state (modified in place).
            repo_path: Resolved repository path.
            cfg: Loop configuration.

        Returns:
            Final loop result.
        """
        profile = analyze_repo(repo_path)
        plan = _detect_asset_plan(profile, cfg.max_assets_per_iteration)

        prev_score = 0.0
        # Track scores per asset for targeting lowest scorers on later iterations
        asset_scores: dict[tuple[str, str], float] = {}

        while not self._should_stop(state, cfg):
            state.iteration += 1
            iteration_scores: list[float] = []
            iteration_pending: list[PendingAsset] = []

            if state.iteration == 1:
                # First iteration: generate entire plan with telemetry context
                targets = plan
            else:
                # Later iterations: only regenerate the bottom 30% by score
                targets = _select_lowest_scorers(asset_scores, cfg)

            for asset_type, name in targets:
                if self._kill_switch:
                    break
                score, pending = self._create_and_queue(
                    asset_type, name, repo_path, profile, state
                )
                if score is not None and pending is not None:
                    iteration_scores.append(score)
                    iteration_pending.append(pending)
                    asset_scores[(asset_type, name)] = score

            if not iteration_scores:
                break

            # Quality gates: schema, security, regression (per-asset)
            gate = _run_quality_gates(iteration_pending, self._queue)
            if not gate.passed:
                logger.warning("Quality gate failed: %s", gate.reason)
                return _finish_loop(state, gate.reason, self._db_path, self._queue)

            # Exclude failed assets from scoring
            passing_scores = [
                s
                for s, p in zip(iteration_scores, iteration_pending, strict=False)
                if p.asset_name not in gate.failed_assets
            ]
            curr_score = (
                sum(passing_scores) / len(passing_scores)
                if passing_scores
                else sum(iteration_scores) / len(iteration_scores)
            )
            state.scores.append(curr_score)

            guard = self._guardrails.check_all(
                state.iteration, cfg, prev_score, curr_score, state.total_cost
            )
            if not guard.passed:
                return _finish_loop(state, guard.reason, self._db_path, self._queue)

            _save_loop_to_db(state, self._db_path)

            if curr_score >= cfg.target_score:
                logger.info(
                    "Init loop reached target score %.1f on iteration %d",
                    curr_score,
                    state.iteration,
                )
                break

            prev_score = curr_score
            _cooldown(cfg.cooldown_seconds)

        return _finish_loop(state, None, self._db_path, self._queue)

    def _improve_loop(
        self, state: LoopState, repo_path: Path, cfg: LoopConfig
    ) -> LoopResult:
        """Execute the improve loop body.

        Args:
            state: Mutable loop state (modified in place).
            repo_path: Resolved repository path.
            cfg: Loop configuration.

        Returns:
            Final loop result.
        """
        prev_score = 0.0

        while not self._should_stop(state, cfg):
            state.iteration += 1
            assets = _find_existing_assets(repo_path)

            if not assets:
                logger.info("Improve loop: no assets found in %s", repo_path)
                break

            scored = _score_existing_assets(assets, cfg.max_assets_per_iteration)
            below = [(p, s) for p, s in scored if s < cfg.target_score]

            if not below:
                logger.info("Improve loop: all assets above target score")
                break

            iteration_scores, iteration_pending = _regenerate_below_threshold(
                below, repo_path, state, self
            )
            if not iteration_scores:
                break

            # Quality gates: schema, security, regression (per-asset)
            gate = _run_quality_gates(iteration_pending, self._queue)
            if not gate.passed:
                logger.warning("Quality gate failed: %s", gate.reason)
                return _finish_loop(state, gate.reason, self._db_path, self._queue)

            passing_scores = [
                s
                for s, p in zip(iteration_scores, iteration_pending, strict=False)
                if p.asset_name not in gate.failed_assets
            ]
            curr_score = (
                sum(passing_scores) / len(passing_scores)
                if passing_scores
                else sum(iteration_scores) / len(iteration_scores)
            )
            state.scores.append(curr_score)

            guard = self._guardrails.check_all(
                state.iteration, cfg, prev_score, curr_score, state.total_cost
            )
            if not guard.passed:
                return _finish_loop(state, guard.reason, self._db_path, self._queue)

            _save_loop_to_db(state, self._db_path)

            prev_score = curr_score
            _cooldown(cfg.cooldown_seconds)

        return _finish_loop(state, None, self._db_path, self._queue)

    def _watch_loop(
        self, state: LoopState, repo_path: Path, cfg: LoopConfig
    ) -> LoopResult:
        """Execute the watch loop body.

        Args:
            state: Mutable loop state (modified in place).
            repo_path: Resolved repository path.
            cfg: Loop configuration.

        Returns:
            Final loop result.
        """
        mtimes: dict[str, float] = {}
        start = time.monotonic()

        while not self._should_stop(state, cfg):
            elapsed = time.monotonic() - start
            if elapsed > cfg.max_runtime_seconds:
                return _finish_loop(
                    state, "Max runtime exceeded", self._db_path, self._queue
                )

            changed = _detect_changed_assets(repo_path, mtimes)
            if changed:
                state.iteration += 1
                iteration_scores, iteration_pending = _regenerate_changed(
                    changed, repo_path, state, self
                )
                if iteration_scores:
                    # Quality gates on watch-loop regen (per-asset)
                    gate = _run_quality_gates(iteration_pending, self._queue)
                    if gate.passed:
                        pairs = zip(
                            iteration_scores,
                            iteration_pending,
                            strict=False,
                        )
                        passing_scores = [
                            s
                            for s, p in pairs
                            if p.asset_name not in gate.failed_assets
                        ]
                        curr = (
                            sum(passing_scores) / len(passing_scores)
                            if passing_scores
                            else sum(iteration_scores) / len(iteration_scores)
                        )
                        state.scores.append(curr)

                        guard = self._guardrails.check_all(
                            state.iteration, cfg, 0.0, curr, state.total_cost
                        )
                        if not guard.passed:
                            return _finish_loop(
                                state, guard.reason, self._db_path, self._queue
                            )
                        _save_loop_to_db(state, self._db_path)
                    else:
                        logger.warning(
                            "Watch loop quality gate failed: %s", gate.reason
                        )

            time.sleep(cfg.cooldown_seconds)

        return _finish_loop(state, None, self._db_path, self._queue)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _should_stop(self, _state: LoopState, cfg: LoopConfig) -> bool:
        """Check stop conditions without running full guardrails.

        Args:
            _state: Current loop state (reserved for future use).
            cfg: Loop configuration.

        Returns:
            True if the loop should stop immediately.
        """
        if self._kill_switch or cfg.kill_switch:
            return True
        stop_file = _STOP_DIR / f"{_STOP_FILE_PREFIX}signal"
        if stop_file.exists():
            self._kill_switch = True
            return True
        return False

    def _create_and_queue(
        self,
        asset_type: str,
        name: str,
        repo_path: Path,
        profile: RepoProfile,
        state: LoopState,
    ) -> tuple[float, PendingAsset] | tuple[None, None]:
        """Generate one asset, add it to the approval queue, return its score.

        Uses telemetry and instinct context so the LLM generation benefits
        from learned patterns.

        Args:
            asset_type: Asset type string.
            name: Asset name.
            repo_path: Repository root.
            profile: RepoProfile.
            state: Current loop state.

        Returns:
            ``(score, pending)`` on success, ``(None, None)`` on failure.
        """
        try:
            from reagent.creation.creator import create_asset

            draft = create_asset(
                asset_type,
                repo_path,
                name=name,
                profile=profile,
                use_telemetry=True,
            )
            pending = _build_pending(draft, state.loop_id, state.iteration, None, None)
            self._queue.add(pending)
            state.changes.append(
                ChangeRecord(
                    asset_type=asset_type,
                    asset_name=name,
                    file_path=pending.file_path,
                    new_score=pending.new_score,
                    action="created",
                )
            )
            return pending.new_score, pending
        except (OSError, ValueError, sqlite3.Error) as exc:
            logger.warning("Failed to create %s/%s: %s", asset_type, name, exc)
            return None, None

    def _regen_and_queue(
        self,
        asset_path: Path,
        repo_path: Path,
        prev_score: float,
        state: LoopState,
    ) -> tuple[float, PendingAsset] | tuple[None, None]:
        """Regenerate an asset, add it to the approval queue, return its score.

        Args:
            asset_path: Path to the existing asset.
            repo_path: Repository root.
            prev_score: Heuristic score of the existing asset.
            state: Current loop state.

        Returns:
            ``(score, pending)`` on success, ``(None, None)`` on failure.
        """
        try:
            from reagent.creation.creator import regenerate_asset

            prev_content = asset_path.read_text(encoding="utf-8")
            draft = regenerate_asset(asset_path, repo_path)
            pending = _build_pending(
                draft, state.loop_id, state.iteration, prev_content, prev_score
            )
            self._queue.add(pending)
            state.changes.append(
                ChangeRecord(
                    asset_type=draft.asset_type,
                    asset_name=draft.name,
                    file_path=pending.file_path,
                    previous_score=prev_score,
                    new_score=pending.new_score,
                    action="updated",
                )
            )
            return pending.new_score, pending
        except (OSError, ValueError, sqlite3.Error) as exc:
            logger.warning("Failed to regenerate %s: %s", asset_path, exc)
            return None, None


def _select_lowest_scorers(
    asset_scores: dict[tuple[str, str], float],
    cfg: LoopConfig,
) -> list[tuple[str, str]]:
    """Select the bottom 30% of assets by score for re-generation.

    Called on iteration 2+ of the init loop to target only the weakest
    performers rather than regenerating the entire plan.

    Args:
        asset_scores: Map of (asset_type, name) → last known score.
        cfg: Loop config providing the target score and asset limit.

    Returns:
        Subset of (asset_type, name) tuples to regenerate.
    """
    below = [
        (key, score) for key, score in asset_scores.items() if score < cfg.target_score
    ]
    below.sort(key=lambda t: t[1])  # worst first
    cutoff = max(1, len(below) // 3)  # bottom third, at least one
    return [key for key, _ in below[:cutoff]]


def _cooldown(seconds: float) -> None:
    """Sleep for the configured cooldown period.

    Args:
        seconds: Seconds to sleep (clamped to ≥0).
    """
    if seconds > 0:
        time.sleep(seconds)


def _score_existing_assets(
    assets: list[Path], max_count: int
) -> list[tuple[Path, float]]:
    """Score existing asset files using content heuristics.

    Args:
        assets: List of asset paths to score.
        max_count: Maximum assets to return.

    Returns:
        List of (path, score) tuples sorted ascending by score.
    """
    scored: list[tuple[Path, float]] = []
    for path in assets:
        try:
            content = path.read_text(encoding="utf-8")
            score = _score_content(content)
            scored.append((path, score))
        except OSError as exc:
            logger.warning("Cannot read asset %s: %s", path, exc)

    scored.sort(key=lambda t: t[1])
    return scored[:max_count]


def _regenerate_below_threshold(
    below: list[tuple[Path, float]],
    repo_path: Path,
    state: LoopState,
    ctrl: LoopController,
) -> tuple[list[float], list[PendingAsset]]:
    """Regenerate all below-threshold assets.

    Args:
        below: List of (path, score) for assets below target.
        repo_path: Repository root.
        state: Current loop state.
        ctrl: LoopController for ``_regen_and_queue``.

    Returns:
        Tuple of (new scores, pending assets) for successfully regenerated assets.
    """
    scores: list[float] = []
    pending: list[PendingAsset] = []
    for asset_path, prev_score in below:
        if ctrl._kill_switch:
            break
        score, asset = ctrl._regen_and_queue(asset_path, repo_path, prev_score, state)
        if score is not None and asset is not None:
            scores.append(score)
            pending.append(asset)
    return scores, pending


def _detect_changed_assets(
    repo_path: Path, mtimes: dict[str, float]
) -> list[tuple[Path, float]]:
    """Detect which assets have been modified since the last poll.

    Updates ``mtimes`` in place.

    Args:
        repo_path: Repository root.
        mtimes: Map of path string → last known mtime.

    Returns:
        List of (path, old_score) for changed assets (old_score = 0
        for newly-seen files).
    """
    changed: list[tuple[Path, float]] = []
    for asset_path in _find_existing_assets(repo_path):
        key = str(asset_path)
        try:
            mtime = asset_path.stat().st_mtime
        except OSError:
            continue
        if key not in mtimes or mtimes[key] != mtime:
            mtimes[key] = mtime
            changed.append((asset_path, 0.0))
    return changed


def _regenerate_changed(
    changed: list[tuple[Path, float]],
    repo_path: Path,
    state: LoopState,
    ctrl: LoopController,
) -> tuple[list[float], list[PendingAsset]]:
    """Regenerate a batch of changed assets detected by the watch loop.

    Args:
        changed: List of (path, prev_score) tuples.
        repo_path: Repository root.
        state: Current loop state.
        ctrl: LoopController for ``_regen_and_queue``.

    Returns:
        Tuple of (new scores, pending assets) for successfully regenerated assets.
    """
    scores: list[float] = []
    pending: list[PendingAsset] = []
    for asset_path, prev_score in changed:
        if ctrl._kill_switch:
            break
        score, asset = ctrl._regen_and_queue(asset_path, repo_path, prev_score, state)
        if score is not None and asset is not None:
            scores.append(score)
            pending.append(asset)
    return scores, pending


def _finish_loop(
    state: LoopState,
    stop_reason: str | None,
    db_path: Path | None,
    queue: ApprovalQueue,
) -> LoopResult:
    """Finalise and persist the loop state, returning a LoopResult.

    Args:
        state: Loop state to finalise.
        stop_reason: Why the loop stopped (None = natural completion).
        db_path: Database path.
        queue: Approval queue to count pending assets.

    Returns:
        Final LoopResult.
    """
    state.status = "stopped" if stop_reason else "completed"
    state.stop_reason = stop_reason
    _mark_loop_complete(state, stop_reason, db_path)
    return _state_to_result(state, queue)


def _state_to_result(state: LoopState, queue: ApprovalQueue) -> LoopResult:
    """Convert a LoopState into a LoopResult.

    Args:
        state: Completed or failed loop state.
        queue: Approval queue to count pending assets.

    Returns:
        LoopResult summary.
    """
    avg_score = (sum(state.scores) / len(state.scores)) if state.scores else 0.0
    pending_count = len(queue.list_pending())
    total_changes = len(state.changes)
    return LoopResult(
        loop_id=state.loop_id,
        loop_type=state.loop_type,
        iterations=state.iteration,
        assets_generated=total_changes,
        avg_score=round(avg_score, 1),
        total_cost=state.total_cost,
        pending_count=pending_count,
        stop_reason=state.stop_reason,
        status=state.status,
    )
