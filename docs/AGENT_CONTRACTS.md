# Agent Contracts & Extensibility Specification

This document details the functional contract, inputs, outputs, and rule IDs for every agent in the Automated Code Review Board.

---

## 1. Specialist Agent Contracts

### 1.1 Diff Agent
- **Module:** `agents/diff_agent.py`
- **Plugin:** `plugins/diff_plugin.py`
- **Category:** `diff`
- **Input:** `ChangeState.files`, `ChangeState.raw_diff`
- **Output:**
  - `ChangeState.summary`: Populated `ChangeSummary` (intent, files touched, size class, risk areas, AST symbols).
  - Findings:
    - `DIF-SIZE-001` (INFO): Changeset size observation (M/L/XL).
    - `DIF-DEP-001` (INFO): Dependency manifest modified.
    - `DIF-RISK-001` (INFO): High-risk functional domains touched (auth, crypto, database, subprocess, payments).

### 1.2 Style Agent
- **Module:** `agents/style_agent.py`
- **Plugin:** `plugins/style_plugin.py`
- **Category:** `style`
- **Input:** `ChangeState.files` (Evaluates **added lines only**)
- **Output Findings:**
  - `STY-LEN-001` (LOW): Line exceeds configured maximum length.
  - `STY-NAME-001` (LOW): Python function or variable not in `snake_case`.
  - `STY-NAME-002` (LOW): Python class not in `PascalCase`.
  - `STY-DOC-001` (LOW): Missing docstring on public function or class.
  - `STY-COMPLEX-001` (MEDIUM): Cyclomatic complexity exceeds threshold (>10).
  - `STY-DEBUG-001` (LOW): Debug print or `console.log` left in code.
  - `STY-DEAD-001` (LOW): Commented-out dead code detected.
  - `STY-EXCEPT-001` (MEDIUM): Bare `except:` clause used.
  - `STY-IMPORT-001` (LOW): Wildcard import (`from x import *`).
  - `STY-MUTABLE-001` (LOW): Mutable default argument in function signature.
  - `STY-TODO-001` (LOW): Unresolved TODO or FIXME marker.

### 1.3 Security Agent
- **Module:** `agents/security_agent.py`
- **Plugin:** `plugins/security_plugin.py`
- **Category:** `security`
- **Input:** `ChangeState.files`, `ChangeState.raw_diff`
- **Output Findings (Strictly Redacted):**
  - `SEC-SQLI-001` (CRITICAL): Unsanitized string formatting or concatenation in SQL query.
  - `SEC-SECRET-001` (CRITICAL): Hard-coded AWS access key ID.
  - `SEC-SECRET-002` (CRITICAL): Hard-coded GitHub personal access token (`ghp_****`).
  - `SEC-SECRET-003` (CRITICAL): Hard-coded Slack token or webhook URL.
  - `SEC-SECRET-004` (CRITICAL): Hard-coded generic secret or high-entropy credential.
  - `SEC-CMDI-001` (CRITICAL): Command injection via `shell=True` or `os.system()`.
  - `SEC-INSEC-001` (HIGH): Insecure deserialization (`pickle.loads`, `yaml.load`).
  - `SEC-CODE-001` (CRITICAL): Dynamic code execution (`eval()` or `exec()`).
  - `SEC-XSS-001` (HIGH): Cross-Site Scripting via `innerHTML` or `dangerouslySetInnerHTML`.
  - `SEC-CRYPTO-001` (MEDIUM): Deprecated cryptographic hash (`MD5`, `SHA1`).
  - `SEC-TLS-001` (MEDIUM): Disabled TLS certificate verification (`verify=False`).
  - `SEC-CONF-001` (MEDIUM): Production debug mode active (`DEBUG = True`).
  - `SEC-CORS-001` (MEDIUM): Permissive CORS wildcard header (`Access-Control-Allow-Origin: *`).
  - `SEC-DEP-001` (LOW): Unpinned or wildcard dependency version.

### 1.4 Test-Coverage Agent
- **Module:** `agents/test_coverage_agent.py`
- **Plugin:** `plugins/coverage_plugin.py`
- **Category:** `test_coverage`
- **Input:** `ChangeState.files`, optional `coverage_report_path`
- **Output Findings:**
  - `TST-UNTESTED-001` (HIGH): New public class or function introduced with zero corresponding test references.
  - `TST-PARTIAL-001` (MEDIUM): Tested symbol lacks assertion validation.
  - `TST-RATIO-001` (MEDIUM): Change test ratio (test lines / source lines) below threshold (<0.50).

---

## 2. Manager and Remediation Agent Contracts

### 2.1 Reviewer Manager
- **Module:** `agents/reviewer_manager.py`
- **Role:** Fan-in synthesizer.
- **Input:** All findings in `state.agent_results`.
- **Pipeline:**
  1. Deduplicate findings via Token Jaccard overlap + Rule ID + Line proximity.
  2. Identify cross-agent corroborations and assign confidence adjustments.
  3. Sort findings into strict priority order (Severity rank descending, corroboration bonus, confidence, category priority).
  4. Evaluate policy thresholds and output `APPROVE` or `REQUEST_CHANGES`.
- **Output:** `ChangeState.consolidated_review` (`ConsolidatedReview`).

### 2.2 Fix-Suggestion Agent
- **Module:** `agents/fix_suggestion_agent.py`
- **Role:** Synthesis and machine verification of automated remediation patches for review findings.
- **Input:** `state.consolidated_review.priority_order`, `state.files`, `state.raw_diff`.
- **Output:**
  - `ChangeState.suggested_patch` (`SuggestedPatch | None`): Concrete patch for the top finding.
  - `ChangeState.fix_suggestions` (`list[FixSuggestion]`): Priority-ordered list of verified suggestions (or manual guidance) for eligible findings.
- **Modes of Operation:**
  - `offline` mode: Produces no fixes by default (`CRB_FIX_SUGGESTIONS=auto`); produces the rule-based template patch for the rank-1 finding if `CRB_FIX_SUGGESTIONS=always`.
  - `llm` mode (with `CRB_LLM_API_KEY`): Generates per-finding structured replacements via LLM, applies patches to virtual in-memory buffers, runs differential re-review, and emits `FixSuggestion` objects with verified diffs or manual guidance notes.
  - Gated by `should_suggest_fixes(settings)`.

---

## 3. How to Add a New Specialist Agent

Adding a new agent requires zero changes to existing agents:

1. **Create the Plugin:**
   Create `plugins/my_domain_plugin.py` defining analysis heuristics or AST visitors.
2. **Implement the Agent:**
   Create `agents/my_domain_agent.py` inheriting from `BaseAgent`:
   ```python
   from agents.base_agent import BaseAgent
   from core.models import Category, Finding
   from core.state import ChangeState

   class MyDomainAgent(BaseAgent):
       def __init__(self, kernel, settings=None):
           super().__init__(
               name="my_domain_agent",
               description="Analyzes domain specific issues",
               instructions="Inspect code for domain rules",
               category=Category.STYLE,  # or custom category
               kernel=kernel,
               settings=settings,
           )

       async def analyze_deterministic(self, state: ChangeState) -> list[Finding]:
           return []
   ```
3. **Register in Orchestrator:**
   In `core/orchestrator.py`:
   - Instantiate `self.my_agent = MyDomainAgent(kernel=self.kernel, settings=self.settings)`
   - Add `self.my_agent` to `specialists = [...]` in `run_review()`.
4. The Reviewer Manager will automatically deduplicate, corroborate, and rank the new agent's findings.
