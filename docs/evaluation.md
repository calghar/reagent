# Evaluation

AgentGuard measures the quality of Claude Code assets using actual session telemetry, detects regressions, and supports A/B testing for iterative improvement.

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
agentguard evaluate --repo ./my-project
```

This produces a quality report table showing each asset's score, label, and key metrics. The report also summarizes overall counts of healthy, underperforming, and stale assets.

## Regression Detection

AgentGuard detects quality regressions by comparing session metrics against a rolling baseline:

```bash
agentguard check-regression <session-id> --repo ./my-project
```

A regression is flagged when a metric deviates more than 2 standard deviations from the baseline mean. The system reports:

- Which metric regressed
- Current value vs. baseline mean and standard deviation
- Related asset changes that may have caused the regression

Regressions are logged to `~/.agentguard/telemetry/regressions.jsonl`.

## A/B Testing

Test asset changes with controlled A/B experiments:

### 1. Create a Variant

```bash
agentguard variant my-project:agent:reviewer --name v2 --change "Reduced verbosity"
```

This creates a copy of the asset as a variant. Edit the variant file to make your changes.

### 2. Collect Data

Sessions automatically alternate between the original and variant. The telemetry hooks tag each session with the active variant.

### 3. Compare Results

```bash
agentguard compare my-project:agent:reviewer my-project:agent:reviewer-v2
```

This shows quality metrics side by side with a confidence score.

### 4. Promote or Discard

```bash
agentguard promote my-project:agent:reviewer-v2   # Replace original with variant
```

Or discard the variant if the original performs better.

## CI Integration

Run AgentGuard in CI pipelines with `agentguard ci` for automated quality gating:

```bash
agentguard ci                    # Check quality with default threshold (60)
agentguard ci --threshold 70     # Require score >= 70
agentguard ci --mode suggest     # Output suggestions without failing
agentguard ci --json             # JSON output for downstream processing
```

### Exit Codes

| Code | Meaning |
| --- | --- |
| 0 | All checks passed |
| 1 | Assets below quality threshold |
| 2 | Security issues found |

### Drift Detection

Detect stale or missing assets before evaluation:

```bash
agentguard drift --repo ./my-project
```

Reports assets that are outdated, missing recommended files, or haven't been
updated since the repo changed significantly.

## Quality-Aware Rollback

Rollback to the historically best-performing version of an asset:

```bash
agentguard rollback-best my-project:agent:reviewer
```

This shows the version history with quality scores and offers to restore the best-performing snapshot.
