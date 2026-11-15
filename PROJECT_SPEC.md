## 1. Project Summary

**Title:** Automated Code Review Board

**One-line description:** A production-ready multi-agent system that takes a submitted code change (a diff / pull request), fans it out to specialist review agents in parallel, fans their findings back in to a Reviewer Manager, and outputs one consolidated, severity-ranked review with a clear **APPROVE / REQUEST-CHANGES** merge recommendation, plus a concrete, machine-verified patch for the single highest-severity finding.

**Enterprise workflow being automated:** Pull-request code review (the gate before merging code).

### 1.1 Objective (from the brief) and how this project meets it

| Brief requirement | How this project satisfies it | Where in this spec |
|---|---|---|
| Design, build and demonstrate a production-ready multi-agent system automating an enterprise workflow | Pull-request review pipeline with CLI, report output, logging, config, tests, Docker, CI, demo scripts | Sections 3, 12, 13, 14 |
| Defined coordination architecture | **Fan-out / fan-in with a Reviewer Manager**, shared change-state object | Section 5 |
| Framework-based agent development (Microsoft Agent Framework or Semantic Kernel) | Built on **Semantic Kernel (Python)**; every agent is a Semantic Kernel agent backed by kernel plugins (tools) | Sections 4, 6 |
| Grounded retrieval or shared memory | **Both**: shared `ChangeState` (shared memory) **and** a local retrieval knowledge base (style guide, secure-coding rules) that agents must cite | Sections 7, 8 |
| Collaborative task execution across specialised agents | Five agents (+ Fix-Suggestion add-on), concurrent execution, manager-led dedup and ranking, cross-agent corroboration | Sections 6, 9 |
| **Diff Agent**: summarises what the change does and files touched | Separate module `agents/diff_agent.py` | 6.1 |
| **Style Agent**: style and readability issues | Separate module `agents/style_agent.py` | 6.2 |
| **Security Agent**: unsafe patterns and secrets | Separate module `agents/security_agent.py` | 6.3 |
| **Test-Coverage Agent**: is the change tested | Separate module `agents/test_coverage_agent.py` | 6.4 |
| **Reviewer Manager**: fans in, deduplicates, approve / request-changes with priority order | Separate module `agents/reviewer_manager.py` | 6.5, 9 |
| Shared change-state object | `ChangeState` model in `core/state.py` | 7 |
| Findings carry a severity so the manager can rank them | `Finding.severity` enum + rank rules | 7, 9 |
| Output: consolidated review, findings grouped by severity, clear merge recommendation | Markdown + JSON + console report | 10 |
| **Group-of-3 add-on**: Fix-Suggestion Agent proposes a concrete patch for the single highest-severity finding | `agents/fix_suggestion_agent.py` | 6.6 |
| **Novelty** (the "good point" of the project) | **Patch Verification Loop** (the proposed fix is actually applied and re-reviewed by the Style and Security agents before being presented) plus **Cross-Agent Corroboration Scoring** | 11 |

---

## 2. Tech Stack and Constraints

- **Language:** Python 3.11+
- **Agent framework:** `semantic-kernel` (Python SDK). Use its agent abstractions (`ChatCompletionAgent`), Kernel, and plugins (`@kernel_function`). Pin the version in `requirements.txt` and verify the imports work after install. If a documented API differs from this spec, follow the installed package's actual API while keeping the architecture unchanged.
- **Data models:** `pydantic` v2.
- **Diff parsing:** `unidiff`.
- **Retrieval:** local, offline-capable. Use `scikit-learn` TF-IDF (default) over the knowledge base documents. Optional upgrade: embeddings via the configured model provider. Retrieval must work with **no API key**.
- **CLI:** `typer`. **Console rendering:** `rich`.
- **Config:** `pydantic-settings` + `.env` file.
- **Testing:** `pytest`, `pytest-asyncio`, `pytest-cov`.
- **Lint/format for the project itself:** `ruff`, `black`, type hints throughout, `mypy` clean on `core/` and `agents/`.
- **Concurrency:** `asyncio` (`asyncio.gather` / `TaskGroup`) for fan-out.
- **Optional UI:** a minimal `streamlit` page (Phase 9, optional) that accepts a pasted diff and shows the report.

### 2.1 Two execution modes (important for reliability and demos)

The system must run in both modes, selectable by config/CLI flag `--mode`:

1. **`offline` (deterministic):** Each agent uses its rule-based tool plugins only (regex, AST, heuristics, retrieval). No network and no API key required. Used for tests, CI and a guaranteed-to-work demo.
2. **`llm` (LLM-enhanced):** Each Semantic Kernel agent additionally calls a chat-completion model (configured through environment variables: provider, model name, API key, endpoint) to reason over the tool findings, add semantic findings, and write natural-language explanations. The model must be instructed to return **strict JSON** matching the `Finding` schema; invalid JSON must be retried once, then fall back to the offline findings for that agent.

Rule: **offline findings are always produced**; LLM mode only augments them. If the LLM call fails, the review still completes (graceful degradation) and the report notes which agents ran degraded.

---

## 3. Repository Layout

Create exactly this structure (add files if needed, but keep each agent as its own module):

```
code-review-board/
├── README.md
├── requirements.txt
├── pyproject.toml
├── .env.example
├── .gitignore
├── Dockerfile
├── Makefile
├── .github/workflows/ci.yml
├── config/
│   ├── settings.py              # pydantic-settings, env loading
│   └── severity_policy.yaml     # severity rubric + merge-decision thresholds
├── core/
│   ├── __init__.py
│   ├── models.py                # Finding, Severity, Category, FileChange, Recommendation, etc.
│   ├── state.py                 # ChangeState (shared change-state object)
│   ├── diff_loader.py           # load diff from file / git range / stdin
│   ├── kernel_factory.py        # builds Semantic Kernel instance + model service (or offline stub)
│   ├── orchestrator.py          # fan-out / fan-in coordination
│   ├── retrieval.py             # knowledge base index + search
│   ├── dedup.py                 # finding similarity + merge logic
│   ├── ranking.py               # severity ranking + risk score
│   ├── patch_tools.py           # apply/verify unified-diff patches
│   └── logging_setup.py
├── agents/
│   ├── __init__.py
│   ├── base_agent.py            # common agent base (SK agent wrapper, timing, error handling)
│   ├── diff_agent.py
│   ├── style_agent.py
│   ├── security_agent.py
│   ├── test_coverage_agent.py
│   ├── reviewer_manager.py
│   └── fix_suggestion_agent.py
├── plugins/                     # Semantic Kernel plugins (deterministic tools used by agents)
│   ├── diff_plugin.py
│   ├── style_plugin.py
│   ├── security_plugin.py
│   ├── coverage_plugin.py
│   └── retrieval_plugin.py
├── knowledge_base/              # grounding documents (retrieval corpus)
│   ├── style/
│   │   ├── python_style_rules.md
│   │   ├── javascript_style_rules.md
│   │   └── readability_guidelines.md
│   ├── security/
│   │   ├── owasp_top10_summary.md
│   │   ├── secrets_patterns.md
│   │   ├── injection_and_unsafe_apis.md
│   │   └── secure_fix_recipes.md
│   └── testing/
│       └── test_coverage_guidelines.md
├── reporting/
│   ├── markdown_report.py
│   ├── json_report.py
│   └── console_report.py
├── cli/
│   └── main.py                  # `review` command
├── samples/
│   ├── diffs/
│   │   ├── 01_clean_change.diff
│   │   ├── 02_sql_injection_and_secret.diff
│   │   ├── 03_untested_feature.diff
│   │   ├── 04_style_mess.diff
│   │   └── 05_mixed_realistic.diff
│   └── expected/                # golden JSON outputs for regression tests
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── docs/
│   ├── ARCHITECTURE.md
│   ├── AGENT_CONTRACTS.md
│   ├── SEVERITY_POLICY.md
│   └── DEMO_SCRIPT.md
└── output/                      # generated reports (gitignored)
```

---

## 4. Framework Usage Requirements (Semantic Kernel)

1. `core/kernel_factory.py` creates a `Kernel`. In `llm` mode it registers a chat completion service from environment config; in `offline` mode it registers a lightweight local stub service so agent code paths stay identical.
2. Each agent in `agents/` is a Semantic Kernel agent (`ChatCompletionAgent`) with:
   - a clear **name**, **description** and **system instructions** (the agent's role, output schema, severity rules, and the rule "ground every finding in a rule from the knowledge base where possible"),
   - its own **plugins** (deterministic `@kernel_function` tools from `plugins/`),
   - an `async run(state: ChangeState) -> AgentResult` method defined in the shared `BaseAgent`.
3. Plugins hold all deterministic analysis logic so results are reproducible and testable without a model.
4. The orchestrator uses framework agents but controls the topology itself (fan-out/fan-in), as described in Section 5. It may optionally use the framework's concurrent orchestration support if available, but the manager logic must remain in `reviewer_manager.py`.
5. Add a short section in `docs/ARCHITECTURE.md` stating exactly which framework classes are used and where.

---

## 5. Coordination Architecture: Fan-Out / Fan-In with Reviewer Manager

```
                    ┌──────────────────────┐
   Submitted diff ─▶│  Diff Loader/Parser  │
                    └──────────┬───────────┘
                               ▼
                    ┌──────────────────────┐
                    │ ChangeState (shared) │◀───────────────┐
                    └──────────┬───────────┘                │ read/write
        ┌──────────────┬───────┴────────┬───────────────┐   │
        ▼   FAN-OUT    ▼                ▼               ▼   │
 ┌────────────┐ ┌─────────────┐ ┌───────────────┐ ┌────────────────┐
 │ Diff Agent │ │ Style Agent │ │ Security Agent│ │ Test-Coverage  │
 └─────┬──────┘ └──────┬──────┘ └───────┬───────┘ └───────┬────────┘
       └───────────────┴───────┬────────┴─────────────────┘
                               ▼   FAN-IN
                    ┌──────────────────────┐
                    │   Reviewer Manager   │  dedup → corroborate → rank → decide
                    └──────────┬───────────┘
                               ▼
                    ┌──────────────────────┐
                    │ Fix-Suggestion Agent │  patch for the #1 finding
                    └──────────┬───────────┘
                               ▼
                    ┌──────────────────────┐
                    │ Patch Verification   │  apply patch → re-run Style + Security
                    └──────────┬───────────┘
                               ▼
                  Consolidated Review (MD / JSON / console)
```

**Rules:**

- The four specialist agents run **concurrently** (true fan-out). Each receives the same read-only view of the change and writes only its own results into its own slot of `ChangeState`.
- A per-agent **timeout** (config, default 60s) and **error isolation**: one agent failing must not crash the review. Its failure is recorded in `ChangeState.agent_status` and shown in the report.
- The Reviewer Manager only starts after all four agents have finished, timed out or failed (fan-in barrier).
- The Fix-Suggestion Agent runs **after** the manager, because it needs the final ranked list.
- The orchestrator logs a structured timeline (agent start/end, durations, finding counts) to prove concurrency in the demo.

---

## 6. Agent Specifications (each is a separate module)

All agents inherit from `BaseAgent` (`agents/base_agent.py`), which provides: timing, structured logging, timeout handling, exception capture into `AgentResult`, and the LLM-augmentation hook with JSON validation and one retry.

### 6.1 Diff Agent (`agents/diff_agent.py`, plugin `plugins/diff_plugin.py`)

**Purpose:** Summarise what the change does and which files it touches.

**Tools / logic:**
- Per-file stats: path, change type (added / modified / deleted / renamed), language (by extension), lines added, lines removed, hunks count.
- Overall stats: total files, total +/- lines, languages involved, whether tests / config / docs / dependency files are touched, and a **change size class** (XS/S/M/L/XL by thresholds in config).
- Classification of file roles: `source`, `test`, `config`, `docs`, `dependency`, `build`, `other`.
- **Intent summary:** in `llm` mode a 3–5 sentence plain-English summary of what the change does and why it likely exists. In `offline` mode a template-based summary built from the stats and detected symbols (new/changed function and class names extracted from added lines).
- Detect **risky areas touched** (auth, crypto, payments, database, file I/O, network, subprocess) by path/keyword heuristics, and store them in `ChangeState.risk_areas` so other agents and the manager can use them.

**Output:** `ChangeSummary` (stored in `ChangeState.summary`) and optional INFO-level findings (for example "very large change, consider splitting", "dependency file changed").

### 6.2 Style Agent (`agents/style_agent.py`, plugin `plugins/style_plugin.py`)

**Purpose:** Check style and readability issues **only on added/changed lines** (never blame untouched code).

**Checks (at minimum):**
- Line length over the configured limit.
- Naming conventions (snake_case functions/variables, PascalCase classes, UPPER_CASE constants for Python; camelCase for JS).
- Missing docstrings/comments on new public functions/classes.
- Function too long (lines) and high cyclomatic complexity (use Python `ast` for Python files; heuristic for others).
- Too many parameters, deep nesting, very long files.
- Dead/commented-out code, leftover `print`/`console.log` debug statements, `TODO/FIXME` without ticket.
- Bare `except:`, wildcard imports, mutable default arguments, magic numbers.
- Trailing whitespace, mixed tabs/spaces, missing newline at end of file.
- Duplicate-looking code blocks inside the change.

**Grounding:** each finding includes `rule_id` and `evidence_source` pointing to the matching knowledge-base section found via the retrieval plugin (for example `style/python_style_rules.md#naming`).

**Severity guidance:** most style findings are `LOW`; `INFO` for suggestions; `MEDIUM` only for readability issues that materially hurt maintainability (very high complexity, huge function, bare `except`).

### 6.3 Security Agent (`agents/security_agent.py`, plugin `plugins/security_plugin.py`)

**Purpose:** Check unsafe patterns and secrets in added/changed lines.

**Secret detection:**
- Regex library for: AWS access keys, generic API keys, private key blocks, JWTs, database connection strings with passwords, Slack/GitHub-style tokens, hard-coded `password = "..."` assignments.
- High-entropy string detector (Shannon entropy threshold in config) on string literals.
- Redact the secret value in findings (show only first 4 chars + `****`). **Never print a full secret in any report or log.**
- Severity: confirmed secret = `CRITICAL`.

**Unsafe patterns (Python and JS focus):**
- SQL built via string formatting/concatenation/f-strings (injection) → `CRITICAL`/`HIGH`.
- `eval`, `exec`, `pickle.loads` on untrusted data, `yaml.load` without safe loader, `subprocess` with `shell=True`, `os.system` with variable input, `innerHTML`/`dangerouslySetInnerHTML`, `document.write`.
- Weak crypto (`md5`, `sha1` for security use, `random` for tokens), disabled TLS verification (`verify=False`), hard-coded `DEBUG=True`, permissive CORS (`*`), insecure deserialization, path traversal via unsanitised path join, hard-coded IPs/URLs with credentials.
- Dependency file changes: flag unpinned or newly added dependencies for review (`MEDIUM`/`LOW`).
- Use `risk_areas` from the Diff Agent to raise one severity level for issues inside auth/crypto/payment code.

**Grounding:** findings carry `rule_id` mapped to an OWASP category (for example `A03:2021-Injection`) and an `evidence_source` from `knowledge_base/security/`.

### 6.4 Test-Coverage Agent (`agents/test_coverage_agent.py`, plugin `plugins/coverage_plugin.py`)

**Purpose:** Determine whether the change is tested.

**Logic:**
- Identify changed source files and changed test files (by path convention: `tests/`, `test_*.py`, `*_test.py`, `*.spec.js`, `*.test.ts`).
- Extract **new/modified public functions and classes** from added lines (Python `ast` where possible).
- For each new/modified symbol, search the diff's test files for references (name matching, import matching). Produce a **per-symbol coverage map**: `tested`, `partially tested` (only referenced, no assertion), `untested`.
- Compute a **change test ratio** (test lines added / source lines added) and an **estimated tested-symbol percentage**.
- Check test quality signals in added tests: has assertions, not just `pass`, covers error path (for example `pytest.raises`), edge-case words.
- If a coverage report file (`coverage.xml` or `coverage.json`) is supplied via `--coverage-report`, parse it and use real line-coverage on changed lines, labelled `measured`; otherwise label results `estimated`.
- Severity: new business logic with zero tests = `HIGH`; partially tested = `MEDIUM`; docs/config-only change with no tests = no finding; trivial change without tests = `LOW`.

### 6.5 Reviewer Manager (`agents/reviewer_manager.py`)

**Purpose:** Fan-in. Combine all findings into one consolidated review.

**Pipeline (implemented in `core/dedup.py` and `core/ranking.py`, orchestrated by the manager):**
1. **Collect** findings and statuses from all agents out of `ChangeState`.
2. **Deduplicate:** two findings are duplicates if they share file and overlapping line range **and** (same `rule_id` OR text similarity above threshold, using normalised token Jaccard/TF-IDF cosine). Merge them into one finding, keep the highest severity, union `reported_by`, concatenate distinct evidence, keep the best recommendation text.
3. **Corroborate (novelty part, see Section 11):** if two or more different agents flag the same location, record `corroborated_by` and raise the **confidence** score; optionally raise severity one level when policy allows.
4. **Rank:** sort by severity (CRITICAL > HIGH > MEDIUM > LOW > INFO), then confidence, then category priority (security > test-coverage > style > diff), then file path/line. Assign sequential `priority_rank` starting at 1.
5. **Group** findings by severity for the report.
6. **Decide:** apply `config/severity_policy.yaml`:
   - Any `CRITICAL` → **REQUEST_CHANGES**.
   - Any `HIGH` → **REQUEST_CHANGES**.
   - Weighted risk score above threshold → **REQUEST_CHANGES**.
   - Otherwise → **APPROVE** (listing remaining MEDIUM/LOW items as non-blocking suggestions).
   - Only two decisions exist: `APPROVE` and `REQUEST_CHANGES`.
7. **Explain the decision:** a "Why this decision" paragraph listing the blocking findings (by rank) and what must change before merge, plus a **merge-risk score (0–100)**.
8. Produce the final `ConsolidatedReview` object (Section 7) and store it in `ChangeState.consolidated_review`.

In `llm` mode the manager may also write the executive summary in natural language, but the decision itself is always computed by deterministic policy (the model cannot override the policy result).

### 6.6 Fix-Suggestion Agent (`agents/fix_suggestion_agent.py`) — Group-of-3 add-on

**Purpose:** Propose a **concrete patch** for the **single highest-severity finding** (rank 1) only.

**Behaviour:**
- Input: the rank-1 finding, the relevant file content/hunk, and matching "secure fix recipes" retrieved from `knowledge_base/security/secure_fix_recipes.md` (or style recipes).
- Output: a `SuggestedPatch` containing: target file, a **unified-diff patch** (valid `diff -u` format), a short explanation, any new imports required, and any follow-up the author must do (for example "rotate the leaked key").
- `offline` mode: template-based fixes for known rule IDs (parameterised SQL queries, secret → environment variable lookup, `shell=True` → argument list, `yaml.load` → `yaml.safe_load`, `verify=False` → remove, `md5` → `sha256`, bare `except` → `except Exception`, add a skeleton unit test for an untested function).
- `llm` mode: the model proposes the patch using the retrieved recipe as grounding; the output is validated by the Patch Verification Loop (Section 11) and falls back to the template fix if it fails verification.
- If no safe automatic patch is possible (for example an architectural issue), return `patch=None` with a clear explanation and manual guidance. Never fabricate a patch that does not apply.

---

## 7. Data Models and Shared Change-State (`core/models.py`, `core/state.py`)

Use pydantic v2 models.

```python
class Severity(str, Enum):      # ordered
    CRITICAL = "CRITICAL"; HIGH = "HIGH"; MEDIUM = "MEDIUM"; LOW = "LOW"; INFO = "INFO"

class Category(str, Enum):
    DIFF = "diff"; STYLE = "style"; SECURITY = "security"; TEST_COVERAGE = "test_coverage"

class Finding(BaseModel):
    id: str                       # stable hash of (category, rule_id, file, line_start)
    category: Category
    severity: Severity
    title: str
    description: str
    file_path: str | None
    line_start: int | None
    line_end: int | None
    code_snippet: str | None      # secrets must be redacted
    rule_id: str                  # e.g. "SEC-SQLI-001", "STY-NAME-003", "TST-UNTESTED-001"
    evidence_source: str | None   # knowledge-base citation (file#section)
    recommendation: str
    confidence: float             # 0.0-1.0
    reported_by: list[str]        # agent names (more than one after merge)
    corroborated_by: list[str] = []
    priority_rank: int | None = None

class FileChange(BaseModel): path, change_type, language, role, lines_added, lines_removed, hunks (with added/removed line numbers and text)

class ChangeSummary(BaseModel): title, intent_summary, files: list[FileChange], totals, languages, size_class, risk_areas

class AgentResult(BaseModel): agent_name, status ("ok" | "degraded" | "failed" | "timeout"), findings, duration_ms, error, mode

class SuggestedPatch(BaseModel): finding_id, file_path, unified_diff, explanation, new_imports, followups, verification: PatchVerification | None

class PatchVerification(BaseModel): applies_cleanly: bool, syntax_ok: bool, original_finding_resolved: bool, new_findings_introduced: list[Finding], verdict: "VERIFIED" | "PARTIAL" | "REJECTED"

class ConsolidatedReview(BaseModel): decision ("APPROVE" | "REQUEST_CHANGES"), decision_reason, merge_risk_score, findings_by_severity: dict[Severity, list[Finding]], priority_order: list[Finding], stats (counts per severity/category, duplicates removed), agent_status, suggested_patch
```

**`ChangeState` (the shared change-state object):**
- `change_id`, `submitted_at`, `source` (file/git range), `raw_diff`, `files: list[FileChange]`
- `summary: ChangeSummary | None`, `risk_areas: list[str]`
- `agent_results: dict[str, AgentResult]` (each agent writes only its own key)
- `all_findings` (read-only property aggregating agent results)
- `agent_status`, `consolidated_review`, `suggested_patch`
- `retrieval` handle (shared knowledge-base search interface)
- `timeline: list[TimelineEvent]` (for orchestration proof)
- Thread/async-safe write methods (use an `asyncio.Lock`); expose a read-only snapshot to agents.
- Serialisable to JSON (`state.model_dump_json()`) so the full state can be saved with the report.

---

## 8. Grounded Retrieval / Shared Memory (`core/retrieval.py`, `plugins/retrieval_plugin.py`)

**Shared memory:** `ChangeState` is the shared memory for a run (all agents read the change; results are posted back; the manager reads everything).

**Grounded retrieval:**
- At start-up, load all Markdown files in `knowledge_base/`, split into sections by headings (each chunk has `doc`, `section`, `text`), and build a TF-IDF index.
- `retrieval.search(query, top_k=3, category_filter=None)` returns chunks with scores and citations (`doc#section`).
- Exposed to every agent as a Semantic Kernel plugin function `search_knowledge_base`.
- **Grounding rule:** every Style and Security finding must try to attach an `evidence_source`. Findings with a retrieved citation get a small confidence boost; findings with none are marked `ungrounded` in the report so reviewers can see which claims have documentary backing.
- Knowledge-base content must be **written fully and meaningfully** (not placeholders): at least 15–25 concise rules/recipes in the security docs, 15+ rules in the style docs, and clear guidelines in the testing doc. Each rule has an ID matching the `rule_id` values used by the plugins.

---

## 9. Severity Policy (`config/severity_policy.yaml` + `docs/SEVERITY_POLICY.md`)

| Severity | Meaning | Examples | Blocks merge? |
|---|---|---|---|
| CRITICAL | Exploitable now / secret leaked / data loss | hard-coded secret, SQL injection | Yes |
| HIGH | Serious defect or risk, likely must fix | `shell=True` with user input, new logic fully untested | Yes |
| MEDIUM | Should fix soon | partial test coverage, bare except, high complexity | No (unless score threshold exceeded) |
| LOW | Minor style/readability | line length, naming | No |
| INFO | Observation | large change, dependency touched | No |

Weights for the risk score (configurable): CRITICAL=40, HIGH=20, MEDIUM=8, LOW=2, INFO=0, capped at 100, then multiplied by `(1 + 0.1 * corroboration_count)` for corroborated findings (cap at 100). Threshold for REQUEST_CHANGES by score: default 30.

All thresholds, weights and decision rules must be read from the YAML file, not hard-coded.

---

## 10. Required Output: Consolidated Review

The system must output, per review, three artefacts in `output/<change_id>/`:

1. `review.md`: human-readable report (primary deliverable).
2. `review.json`: full machine-readable `ConsolidatedReview` + `ChangeState` snapshot.
3. Console output via `rich` (same content, colour-coded).

**`review.md` structure (exact section order):**

1. **Header:** title, change ID, timestamp, mode (offline/llm), source.
2. **Merge Recommendation:** a prominent banner: `✅ APPROVE` or `❌ REQUEST CHANGES`, merge-risk score, and a 2–4 sentence "Why this decision".
3. **Change Summary (from Diff Agent):** what the change does, files touched table (path, type, +/-, role), size class, risk areas.
4. **Findings by Severity:** sections `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFO`; each finding shows rank number, title, category, file:line, snippet (redacted), explanation, recommendation, rule ID, evidence citation, confidence, reported-by / corroborated-by. Empty severity sections show "None".
5. **Priority Order (Fix First):** numbered list of all findings in rank order with a one-line description each.
6. **Test Coverage Map:** per-symbol table (symbol, file, tested / partial / untested) and the change test ratio.
7. **Suggested Fix for Top Finding (Fix-Suggestion Agent):** explanation, the unified-diff patch in a code block, follow-ups, and the **Patch Verification result** (Section 11).
8. **Agent Execution Report:** table of agents with status, duration, findings count, degraded/failed notes, and the fan-out/fan-in timeline (proof of concurrency).
9. **Statistics:** totals per severity and category, duplicates removed, corroborated findings count.

---

## 11. Novelty: Patch Verification Loop + Cross-Agent Corroboration

This is the project's distinguishing feature; implement it completely and demonstrate it.

### 11.1 Patch Verification Loop ("Fix-and-Re-Review")
Most review tools only *suggest* fixes. This system **proves** the suggested fix is safe before showing it:

1. The Fix-Suggestion Agent produces a unified-diff patch for the rank-1 finding.
2. `core/patch_tools.py` applies the patch **in memory / to a temp copy** of the affected file(s) (never to the user's real files) and checks that it **applies cleanly**.
3. **Syntax check:** parse the patched file (`ast.parse` for Python; a lightweight check for others).
4. **Re-review:** run the Style and Security plugins on the patched content.
5. Verify (a) the **original finding no longer appears** and (b) **no new CRITICAL/HIGH findings were introduced**.
6. Record a `PatchVerification` verdict: `VERIFIED` (all pass), `PARTIAL` (applies but minor new issues), or `REJECTED` (does not apply / broken / still vulnerable).
7. If `REJECTED`, retry once with the template fix; if still rejected, show the manual guidance instead and say so honestly in the report.

### 11.2 Cross-Agent Corroboration Scoring
When independent agents flag the same file/line region (for example Security flags an f-string SQL query and Style flags a risky long query-building line, or Test-Coverage flags an untested function that Security flagged as unsafe), the manager records `corroborated_by`, increases confidence, and surfaces a "Corroborated by N agents" badge in the report. This makes the priority ranking more trustworthy and demonstrates real multi-agent collaboration instead of independent parallel scripts.

### 11.3 Demonstration requirement
`samples/diffs/02_sql_injection_and_secret.diff` must trigger both features visibly: a CRITICAL finding whose patch is `VERIFIED`, and at least one corroborated finding.

---

## 12. Build Phases and Tasks

Complete phases in order. Each phase ends with an **Exit check**. Commit after each phase with a clear message.

### Phase 0: Project Bootstrap
- Create the repository layout (Section 3), `requirements.txt`, `pyproject.toml`, `.gitignore`, `.env.example`, `Makefile` (targets: `install`, `test`, `lint`, `demo`, `review`).
- Set up virtual environment instructions, `ruff`/`black`/`mypy` configs.
- Implement `core/logging_setup.py` and `config/settings.py` (reads env: mode, model provider/name/key, timeouts, thresholds).
- **Exit check:** `make install && make lint` passes on the empty skeleton; `python -c "import semantic_kernel"` works.

### Phase 1: Core Models and Shared State
- Implement all models in `core/models.py` and `ChangeState` in `core/state.py` (Section 7).
- Implement `core/diff_loader.py` (diff from file path, stdin, or `git diff <base>..<head>` in a repo) and parse with `unidiff` into `FileChange` objects with added-line numbers.
- Unit tests for models (serialisation, severity ordering, finding id stability) and diff parsing (added/modified/deleted/renamed, multiple hunks, binary file skipped).
- **Exit check:** tests pass; loading each sample diff produces a valid `ChangeState`.

### Phase 2: Knowledge Base and Retrieval
- Write all knowledge-base Markdown files with real content and rule IDs (Section 8).
- Implement `core/retrieval.py` (TF-IDF index, `search`, citations) and `plugins/retrieval_plugin.py`.
- Unit tests: known queries return the expected rule chunk in top-3 (for example "sql injection string formatting" → `injection_and_unsafe_apis.md`).
- **Exit check:** retrieval works offline; ≥90% of rule-ID lookups in tests succeed.

### Phase 3: Framework Setup and Base Agent
- Implement `core/kernel_factory.py` (offline stub + LLM service) and `agents/base_agent.py` (timeouts, error capture, JSON-validated LLM augmentation with one retry, degraded-mode handling).
- Smoke test: a trivial agent runs in both modes (LLM mode skipped automatically when no key is present).
- **Exit check:** `BaseAgent` subclass runs, returns an `AgentResult`, handles a forced exception and a forced timeout without crashing.

### Phase 4: Diff Agent
- Implement `plugins/diff_plugin.py` and `agents/diff_agent.py` (Section 6.1).
- Tests: stats correctness, file role classification, risk-area detection, size class, symbol extraction.
- **Exit check:** every sample diff yields a correct `ChangeSummary`.

### Phase 5: Style Agent
- Implement `plugins/style_plugin.py` and `agents/style_agent.py` (Section 6.2) with grounded citations.
- Tests: one positive and one negative test per rule; verify only **added lines** are flagged.
- **Exit check:** `04_style_mess.diff` yields the expected style findings; `01_clean_change.diff` yields none or only INFO.

### Phase 6: Security Agent
- Implement `plugins/security_plugin.py` and `agents/security_agent.py` (Section 6.3) including secret redaction and entropy detection.
- Tests: each secret pattern and each unsafe pattern; confirm secrets are **never** printed in full anywhere (assert on log output and reports).
- **Exit check:** `02_sql_injection_and_secret.diff` yields CRITICAL findings for the secret and the SQL injection.

### Phase 7: Test-Coverage Agent
- Implement `plugins/coverage_plugin.py` and `agents/test_coverage_agent.py` (Section 6.4), including optional coverage-report parsing.
- Tests: symbol mapping tested/partial/untested; ratio calculation; docs-only change produces no finding.
- **Exit check:** `03_untested_feature.diff` yields HIGH untested-logic findings; changes that include proper tests do not.

### Phase 8: Orchestrator (Fan-Out / Fan-In) and Reviewer Manager
- Implement `core/orchestrator.py`: concurrent fan-out of the four agents, per-agent timeout and isolation, fan-in barrier, timeline recording.
- Implement `core/dedup.py`, `core/ranking.py`, and `agents/reviewer_manager.py` (Section 6.5) with policy loaded from `severity_policy.yaml`.
- Tests: duplicate merging, ranking order, decision rules (each rule path), corroboration, one agent failing still yields a review, concurrency test (total wall time ≈ slowest agent, not the sum, using artificial delays).
- **Exit check:** end-to-end run on all samples produces a `ConsolidatedReview` with correct decisions (01 → APPROVE; 02, 03 → REQUEST_CHANGES).

### Phase 9: Fix-Suggestion Agent and Patch Verification Loop (Group-of-3 add-on + Novelty)
- Implement `core/patch_tools.py` and `agents/fix_suggestion_agent.py` (Sections 6.6, 11).
- Template fixes for all supported rule IDs; verification loop with the three verdicts; retry/fallback logic.
- Tests: patch applies cleanly; verification detects a deliberately broken patch (`REJECTED`) and a still-vulnerable patch; the real user files are never modified.
- **Exit check:** sample 02's top finding gets a `VERIFIED` patch; the report shows it.

### Phase 10: Reporting and CLI
- Implement `reporting/markdown_report.py`, `json_report.py`, `console_report.py` following Section 10 exactly.
- Implement `cli/main.py` with `typer`:
  - `review --diff <file>` / `review --git <base>..<head>` / `review --stdin`
  - options: `--mode offline|llm`, `--coverage-report <path>`, `--output-dir`, `--format md|json|both`, `--fail-on-request-changes` (exit code 1 when the decision is REQUEST_CHANGES, for CI use), `--verbose`.
  - `demo` command: runs all five samples and prints a summary table.
- **Exit check:** `python -m cli.main review --diff samples/diffs/05_mixed_realistic.diff` writes `review.md` + `review.json` and prints the console report.

### Phase 11: Testing, Quality, and Hardening
- Integration tests for each sample diff against golden outputs in `samples/expected/` (compare decision, severity counts and top-finding rule ID, not volatile fields).
- Coverage target: **≥ 85%** line coverage for `core/` and `agents/` (`pytest --cov`).
- Edge cases: empty diff, binary-only diff, huge diff (truncate safely with a warning), non-UTF-8 content, unsupported language (graceful INFO), malformed diff (clear error).
- Security hardening for the tool itself: never execute submitted code; never write outside `output/`; redact secrets in logs; sanitise file paths.
- **Exit check:** `make test` green; coverage target met; `ruff`, `black --check`, `mypy` clean.

### Phase 12: Packaging, CI and Documentation
- `Dockerfile` (slim Python image, non-root user, entrypoint is the CLI) and `.github/workflows/ci.yml` (install, lint, test with coverage, run the demo in offline mode, upload reports as artefacts).
- Write `README.md` (what it is, architecture diagram, install, quick start, both modes, configuration table, sample output excerpt, how to add a new agent, limitations).
- Write `docs/ARCHITECTURE.md` (coordination architecture, framework classes used, data flow, shared state, failure handling), `docs/AGENT_CONTRACTS.md` (input/output contract per agent), `docs/SEVERITY_POLICY.md`, and `docs/DEMO_SCRIPT.md` (step-by-step live demo script, ~5 minutes, showing fan-out timeline, dedup, corroboration, decision, and the verified patch).
- **Exit check:** a fresh clone can follow the README and run the demo successfully; Docker image builds and runs the demo.

### Phase 13 (Optional): Minimal Web UI
- `ui/app.py` (`streamlit`): paste or upload a diff, choose mode, press **Run Review**, see the recommendation banner, severity-grouped findings, patch and agent timeline. Add `make ui`.
- **Exit check:** UI renders a review for sample 05.

---

## 13. Sample Data Requirements (`samples/diffs/`)

Create realistic unified diffs (not toy one-liners) so the demo is convincing:

| File | Content | Expected outcome |
|---|---|---|
| `01_clean_change.diff` | Small, well-written feature with docstrings, type hints and matching tests | APPROVE, no findings above LOW/INFO |
| `02_sql_injection_and_secret.diff` | New DB access function using an f-string SQL query and a hard-coded API key (use a **fake, obviously dummy** key pattern), no tests | REQUEST_CHANGES; CRITICAL x2; corroboration; verified patch for rank 1 |
| `03_untested_feature.diff` | Substantial new business logic with no test changes | REQUEST_CHANGES; HIGH untested findings |
| `04_style_mess.diff` | Long lines, bad naming, no docstrings, debug prints, commented-out code, bare except, large function | APPROVE or REQUEST_CHANGES based on policy score; many LOW/MEDIUM style findings |
| `05_mixed_realistic.diff` | Multi-file change (Python + JS + config + dependency file) with a mix of all issue types | REQUEST_CHANGES; findings across all categories; dedup visible |

Add a `README` inside `samples/` explaining each file and its expected result. All secrets in samples must be fake.

---

## 14. Non-Functional Requirements (what "production-ready" means here)

- **Reliability:** per-agent timeout, error isolation, graceful degradation, deterministic offline mode, retries only where specified.
- **Observability:** structured logging with a correlation `change_id`; timeline of agent execution in the report; log level via config.
- **Performance:** offline review of a 1,000-line diff completes in under 5 seconds on a normal laptop.
- **Security:** no code execution of submitted content, secret redaction everywhere, safe temp-file handling, no network calls in offline mode.
- **Configurability:** thresholds, weights, mode, timeouts and model settings through config/env only; no magic numbers in code.
- **Maintainability:** each agent is an independent module with a documented contract; adding a new agent requires only a new agent module, a plugin, and one registration line in the orchestrator.
- **Extensibility note:** document how the Fix-Suggestion pattern could extend to multiple findings.

---

## 15. Coding Standards

- Type hints everywhere; docstrings on all public classes/functions.
- No hard-coded secrets, paths or thresholds.
- Small, single-purpose functions; follow the project's own Style Agent rules (the project should pass its own review: run the tool on its own diff as a final dogfooding step and include the report in `docs/`).
- Meaningful commit messages per phase.
- Do not mention any AI assistant or code-generation tool names in any file (see the naming rule at the top).

---

## 16. Demonstration Plan (what must be shown at the end)

1. Run `make demo`; show the five reviews and the summary table.
2. Open `output/.../review.md` for sample 02 and walk through: recommendation banner, severity grouping, priority order, corroborated finding, the verified patch, and the agent timeline showing concurrent execution.
3. Show a forced agent failure (config flag `--simulate-failure security`) to prove graceful degradation.
4. Show offline vs LLM mode (if a key is available).
5. Show the retrieval grounding: a finding with its knowledge-base citation.

---

## 17. Final Acceptance Checklist

All items must be true:

- [ ] Five agents exist as **separate modules**: Diff, Style, Security, Test-Coverage, Reviewer Manager.
- [ ] Add-on: **Fix-Suggestion Agent** exists as a separate module and patches only the single highest-severity finding.
- [ ] Built with **Semantic Kernel**; agents are framework agents with plugins; usage documented.
- [ ] **Fan-out / fan-in** with a Reviewer Manager is implemented, with proof of concurrency in the timeline.
- [ ] A **shared change-state object** is used by all agents.
- [ ] Every finding carries a **severity** and the manager ranks by it.
- [ ] Manager **deduplicates** findings and outputs **APPROVE / REQUEST_CHANGES** with a priority order.
- [ ] Output is a **consolidated review grouped by severity** with a **clear merge recommendation**.
- [ ] **Grounded retrieval** (knowledge base with citations) and shared memory are both implemented.
- [ ] **Novelty** implemented and demonstrated: Patch Verification Loop + Cross-Agent Corroboration.
- [ ] Runs fully **offline** and optionally in LLM mode.
- [ ] Tests pass with ≥85% coverage on `core/` and `agents/`; lint and type checks clean.
- [ ] Docker + CI + full documentation present; a fresh clone can run the demo from the README.
- [ ] No AI assistant or code-generation tool names appear anywhere in the repository.
