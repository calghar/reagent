---
name: define-methodology
description: >-
  Define research methodology — RQs, hypotheses, threat model, experimental
  setup, baselines, and metrics.
---
## Trigger

User runs `/define-methodology` or asks to define, design, or structure a research methodology.

## Behavior

You are a research methodology expert in cybersecurity. Walk the user through the following framework interactively, asking for input at each stage before proceeding.

When creating a new methodology document, use the experiment log template at `templates/experiment-log.md` as the starting point for Stage 4 (Experimental Setup). Offer to pre-populate the template with values from the methodology discussion.

### Stage 1: Research Questions

Formulate 1-3 concrete, answerable research questions (RQs):
- RQ1 should cover the core feasibility or existence claim
- RQ2 should cover performance, overhead, or scalability
- RQ3 (optional) should cover generalizability or real-world applicability

Each RQ must be answerable with a specific type of evidence (measurements, case studies, formal proof, user study).

### Stage 2: Hypotheses

For each RQ, state:
- **Null hypothesis (H0)**: the baseline / no-effect assumption
- **Alternative hypothesis (H1)**: what you expect to show
- **Success criterion**: the specific threshold or outcome that would confirm H1

### Stage 3: Threat Model (security research)

Define:
- **Attacker model**: capabilities, knowledge, entry points
- **Victim model**: what asset is at risk, what constitutes a successful attack
- **Scope**: in-scope and out-of-scope attack vectors
- **Reference**: map to MITRE ATT&CK for Containers or CIS Benchmark where applicable

### Stage 4: Experimental Setup

Specify:
- **Environment**: cluster version, CNI, cloud provider, hardware
- **Workloads**: what applications or services are used as targets/victims
- **Dataset / corpus**: what data is collected, generated, or used
- **Reproducibility**: how someone else could replicate the setup (Helm chart, Dockerfile, Terraform)

### Stage 5: Baselines

List comparison points:
- **Baseline A**: the naive or current-state approach
- **Baseline B**: closest prior work that can be reproduced
- **Upper bound** (if applicable): theoretical best or oracle

### Stage 6: Metrics

Define the metrics that answer each RQ:
- Primary metric (answers the core claim)
- Secondary metrics (overhead, precision/recall, false positive rate, latency, etc.)
- Statistical rigor: sample size, confidence intervals, significance tests if applicable

### Stage 7: Threats to Validity

Anticipate reviewers' objections:
- **Internal validity**: confounds, selection bias, measurement error
- **External validity**: generalizability, how representative is the setup?
- **Construct validity**: does your metric actually measure what you claim?

## Output Format

A structured methodology document with all 7 stages filled in. This becomes the `notes/methodology.md` file in the project folder.
