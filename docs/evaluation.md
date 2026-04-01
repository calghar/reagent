# Evaluation

Reagent measures the quality of Claude Code assets using actual session telemetry, detects regressions, and supports A/B testing for iterative improvement.

## Prerequisites

Install telemetry hooks to collect session data:

```bash
reagent hooks install
```

This adds hook scripts to `~/.claude/settings.json` that log session events (start, tool use, end) to `~/.reagent/events.jsonl`.

## Quality Metrics

The evaluator computes these metrics per asset:

| Metric | Description | Range |
| --- | --- | --- |
| Invocation rate | How often the asset is used per week | 0+ |
| Completion rate | Fraction of invocations that complete successfully | 0–1 |
| Correction rate | Fraction of tool calls followed by corrections | 0–1 |
| Turn efficiency | Average turns to complete a task | 1+ |
| Staleness | Days since the asset was last modified | 0+ |
| Coverage | Fraction of relevant workflows the asset handles | 0–1 |
| Security score | Static analysis pass/fail score | 0–100 |
| Freshness | Recency of last invocation | 0–1 |

These combine into an overall quality score (0–100) with labels:

| Score | Label |
| --- | --- |
| 80–100 | Excellent |
| 60–79 | Good |
| 40–59 | Needs Work |
| 0–39 | Poor |

## Running Evaluations

```bash
reagent evaluate --repo ./my-project
```

This produces a quality report table showing each asset's score, label, and key metrics. The report also summarizes overall counts of healthy, underperforming, and stale assets.

## Autonomous Loop Evaluation

The autonomous loop uses evaluation scores to drive iterative improvement. Reagent supports three loop types:

### Init Loop

Generate all missing assets from scratch, then evaluate and iterate:

```bash
reagent loop init                       # Generate all missing assets
reagent loop init --threshold 85        # Target score of 85
reagent loop init --max-iterations 3    # Limit iterations
reagent loop init --no-approval         # Auto-deploy without review
```

### Improve Loop

Regenerate existing assets that score below a threshold:

```bash
reagent loop improve                    # Regenerate assets scoring below 80
reagent loop improve --threshold 70     # Custom threshold
```

### Watch Loop

Continuously monitor the repo for changes and regenerate assets as needed:

```bash
reagent loop watch                      # Poll every 30 seconds
reagent loop watch --interval 60        # Custom poll interval
```

### How the Loop Works

Each loop iteration follows this cycle until the target score is met or guardrails stop it:

1. **Evaluate** — Score all assets in the repo
2. **Select** — Pick assets below the target threshold
3. **Regenerate** — Use LLM to generate improved versions
4. **Queue** — Stage improved assets for human review
5. **Approve** — Human reviews and deploys approved assets

### Guardrails

Hard limits prevent runaway loops from consuming excessive resources:

| Guardrail | Default | Option | Description |
| --- | --- | --- | --- |
| Max iterations | 5 | `--max-iterations N` | Loop stops after N iterations |
| Max cost | $2.00 | `--max-cost USD` | Loop stops when LLM spend reaches limit |
| Target score | 80 | `--target FLOAT` | Loop stops when average score meets target |
| Min improvement | 5 pts | — | Loop stops if score improvement per iteration is too small |
| Max runtime | 30 min | — | Loop stops after 30 minutes |
| Max assets/iteration | 10 | — | Limits assets regenerated per iteration |
| Human approval | required | `--no-approval` | All changes require human review before deployment |
| Kill switch | off | `reagent loop stop` | Emergency stop for any running loop |

The kill switch creates a sentinel file at `~/.reagent/loop_stop_signal`. Any running loop checks for this file before each iteration.

### Approval Queue

When `require_approval` is enabled (the default), generated assets are queued for review rather than written immediately:

```bash
reagent loop review       # Show pending assets awaiting approval
reagent loop diff         # Show unified diff for pending vs previous version
reagent loop deploy       # Write approved assets to disk
reagent loop discard      # Reject pending changes
```

The approval queue is stored in SQLite and persists across CLI invocations.

### Loop Status and Control

```bash
reagent loop status       # Show current loop state
reagent loop stop         # Activate kill switch to stop a running loop
reagent loop history      # Show last 10 loop runs
```

## Regression Detection

Reagent detects quality regressions by comparing session metrics against a rolling baseline:

```bash
reagent check-regression <session-id> --repo ./my-project
```

A regression is flagged when a metric deviates more than 2 standard deviations from the baseline mean. The system reports:

- Which metric regressed
- Current value vs. baseline mean and standard deviation
- Related asset changes that may have caused the regression

Regressions are logged to `~/.reagent/telemetry/regressions.jsonl`.

### Automated Detection

Install the regression check hook for automatic detection after each session:

```bash
reagent hooks install-agent-hooks
```

This deploys a session evaluator agent that runs on the `Stop` event and checks for regressions.

## A/B Testing

Test asset changes with controlled A/B experiments:

### 1. Create a Variant

```bash
reagent variant my-project:agent:reviewer --name v2 --change "Reduced verbosity"
```

This creates a copy of the asset as a variant. Edit the variant file to make your changes.

### 2. Collect Data

Sessions automatically alternate between the original and variant. The telemetry hooks tag each session with the active variant.

### 3. Compare Results

```bash
reagent compare my-project:agent:reviewer my-project:agent:reviewer-v2
```

This shows quality metrics side by side with a confidence score.

### 4. Promote or Discard

```bash
reagent promote my-project:agent:reviewer-v2   # Replace original with variant
```

Or discard the variant if the original performs better.

## CI Integration

Run Reagent in CI pipelines with `reagent ci` for automated quality gating:

```bash
reagent ci                    # Check quality with default threshold (60)
reagent ci --threshold 70     # Require score >= 70
reagent ci --mode suggest     # Output suggestions without failing
reagent ci --json             # JSON output for downstream processing
```

### Exit Codes

| Code | Meaning |
| --- | --- |
| 0 | All checks passed |
| 1 | Assets below quality threshold |
| 2 | Security issues found |

### GitHub Action

The quickest way to add quality gates to your CI pipeline:

```yaml
- name: Check asset quality
  uses: calghar/reagent@v0.3.0
  with:
    mode: check
    threshold: 70
    security: true
```

See the full [CI Integration guide](ci-integration.md) for action inputs/outputs, example workflows, drift detection, and auto-fix setup.

### Drift Detection

Detect stale or missing assets before evaluation:

```bash
reagent drift --repo ./my-project
```

Reports assets that are outdated, missing recommended files, or haven't been
updated since the repo changed significantly.

## Prompt Hooks

Install quality gate hooks that run during sessions:

```bash
reagent hooks install-prompt-hooks
```

This installs:

- **Convention check** — validates that generated assets follow project conventions
- **Review summary** — generates a quality summary after review sessions

## Dashboard

View asset health in the web dashboard:

```bash
reagent dashboard
```

The dashboard shows:

- Asset quality scores with letter grades
- Trend indicators (improving, stable, declining)
- A/B test status and results
- Recent regression alerts
- Generation cost tracking
- Autonomous loop control

See the [Dashboard guide](dashboard.md) for deployment options, API endpoints, and Docker Compose setup.

## Quality-Aware Rollback

Rollback to the historically best-performing version of an asset:

```bash
reagent rollback-best my-project:agent:reviewer
```

This shows the version history with quality scores and offers to restore the best-performing snapshot.
