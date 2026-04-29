---
name: lit-search
description: >-
  Literature survey with QUICK, DEEP, and SYSTEMATIC modes. Multi-source search
  with anti-hallucination grounding.
---
## Trigger

User runs `/lit-search [topic]` or asks for a literature survey, related work, or paper landscape on a topic.

**MCP dependencies**: `academic-search-mcp-server` (required for DEEP mode), `zotero-mcp` (optional), `tavily-mcp` (optional supplement), `github-mcp-server` (for tool/repo discovery)

## Modes

- **QUICK** (`/lit-search QUICK [topic]`): Return a 5-10 paper summary and gap sketch. Skip GitHub and adjacent concept searches. No related work narrative.
- **DEEP** (default when no mode specified): Full pipeline below. Multi-source. Up to 50+ papers. Related work narrative optional.
- **SYSTEMATIC** (`/lit-search SYSTEMATIC [topic]`): Full DEEP pipeline plus explicit inclusion/exclusion criteria documented and search string logged.

---

## Behavior — QUICK Mode

1. Scope the search (see Step 1 below)
2. Run 2-3 targeted queries on Semantic Scholar (`academic-search-mcp-server`) and arXiv
3. Return: 5-10 most relevant papers (table format), 3-bullet gap sketch
4. Note: "Run `/lit-search DEEP` for a full survey"

Grounding: each paper must be findable via `academic-search-mcp-server` or have a valid arXiv ID that resolves via WebFetch. Do not include papers recalled from training.

---

## Behavior — DEEP Mode

### Step 1: Scope the Search

Parse the topic and identify:
- Core concept (e.g., "eBPF-based runtime detection")
- Adjacent concepts to include (e.g., "syscall monitoring", "kernel observability")
- What to explicitly exclude to keep scope manageable

### Step 2: Search Strategy

Use `academic-search-mcp-server` and WebSearch to query:
- Semantic Scholar (via MCP) — primary for paper metadata and citation counts
- arXiv (cs.CR, cs.SE, cs.NI, cs.DC)
- IEEE Xplore, ACM DL, USENIX
- GitHub (via `github-mcp-server`) — for tools and repos that lack papers
- Zotero library (via `zotero-mcp`, if available) — check team's existing collection

Search queries to run:
1. `[core concept]` on Semantic Scholar
2. `[core concept] site:arxiv.org`
3. `[core concept] USENIX OR IEEE OR CCS OR NDSS`
4. `[core concept] Kubernetes OR "cloud native" OR container`
5. `[adjacent concept] survey OR systematization`
6. `[core concept]` on GitHub (repos, READMEs)

**Grounding rules** (mandatory — prevents hallucinated citations):
- Include a paper only if it was returned by an actual tool call in this session. Do not recall papers from training.
- Before adding a paper to the catalog, use WebFetch to retrieve its abstract page (arXiv, Semantic Scholar, venue page). The fetch must succeed.
- If the fetch fails: mark the entry `[UNVERIFIED]` with the failure reason. Do not infer or fill in missing fields.
- If a field (author, year, venue) was not present on the fetched page: leave it blank or write `[unknown]`.

### Step 3: Categorize Results

Group papers into:
- **Foundational** — seminal works that define the problem or technique
- **Direct related** — papers that address the same problem
- **Adjacent** — papers that use similar techniques for different problems
- **Surveys / SoK** — systematization papers covering the space
- **Tools / Repos** — open-source implementations without an accompanying paper

For each paper include: authors, year, venue, one-sentence contribution, citation count (from Semantic Scholar), and relevance to the research idea.

### Step 4: Gap Analysis

After surveying, answer:
- What problem formulations have been tried and what are their limitations?
- What threat models or assumptions are commonly made that could be challenged?
- What metrics or evaluation setups dominate — and what is missing?
- Where is there an opening for a contribution?

### Step 5: Grounding Check (mandatory before output)

Before producing any output, run a verification pass over the draft catalog:

1. For each paper: confirm which tool call retrieved it. If none, remove it.
2. For each paper: confirm title, first author, and year appear on the fetched page. If not, mark `[UNVERIFIED]` or correct.
3. Count: report "X papers verified, Y [UNVERIFIED]" in the output summary.
4. If more than 20% of papers are `[UNVERIFIED]`, note this prominently — the search may need to be rerun with different queries.

### Step 6: Zotero Import (if `zotero-mcp` available)

Offer to import the top 10 most relevant papers to Zotero by DOI or arXiv ID. Ask the user which Zotero collection to use.

### Step 7: Related Work Narrative (optional)

If the user has a specific idea in mind, draft a 2-3 paragraph related work section that:
1. Contextualizes the problem space
2. Summarizes prior approaches and their shortcomings
3. Positions the user's work relative to the gap

## Output Format

**QUICK**: 1 table (5-10 papers) + 3-bullet gap sketch.

**DEEP**: Structured with headers. Table format for the paper catalog (with citation counts). Gap analysis as bulleted list. Related work narrative as prose (if requested). Summary line: "N papers found; X verified, Y [UNVERIFIED]; M imported to Zotero."
