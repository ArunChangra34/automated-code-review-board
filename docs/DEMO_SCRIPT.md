# Live Demonstration Script: Automated Code Review Board

This guide provides a step-by-step walkthrough to demonstrate the core capabilities of the Automated Code Review Board in under 5 minutes.

---

## Step 1: Run Full Demo on All 5 Sample Diffs (60 seconds)

Execute the end-to-end demo command:

```bash
make demo
# or directly:
python -m cli.main demo
```

### What to highlight to observers:
- **Instant Processing:** All 5 sample changes (touching Python, JavaScript, YAML, and text) are evaluated across 4 concurrent specialist agents in under 0.1 seconds.
- **Summary Table:**
  - `01_clean_change.diff` $\rightarrow$ `APPROVE` (Score: 0/100).
  - `02_sql_injection_and_secret.diff` $\rightarrow$ `REQUEST_CHANGES` (2 CRITICAL, VERIFIED patch).
  - `03_untested_feature.diff` $\rightarrow$ `REQUEST_CHANGES` (4 HIGH untested findings).
  - `04_style_mess.diff` $\rightarrow$ `REQUEST_CHANGES` (High volume of style findings).
  - `05_mixed_realistic.diff` $\rightarrow$ `REQUEST_CHANGES` (Multi-file cross-language review with VERIFIED patch).

---

## Step 2: Deep Dive into Sample 02 Report (90 seconds)

Open the generated markdown report:

```bash
cat output/02_sql_injection_and_secret/review.md
# or run with rich console output:
python -m cli.main review --diff samples/diffs/02_sql_injection_and_secret.diff
```

### Key architectural features to walk through:
1. **Merge Recommendation Banner:**
   Prominent red banner (`🔴 RECOMMENDATION: REQUEST CHANGES`) with explicit reason citing the blocking issues.
2. **Secret Redaction:**
   Show the hard-coded API key finding. Note that the credential is masked (`AKIA****`), proving that secrets never leak into reports or terminal output.
3. **Cross-Agent Corroboration:**
   Point out the `🎯 Corroborated by 2 agents` badge on findings where both Security and Test-Coverage flagged the unreviewed function.
4. **Novelty - Patch Verification Loop:**
   Show the **Suggested Fix for Top Finding**:
   - The unified diff patch replacing the hardcoded secret with `os.environ`.
   - The verification status: `🟢 VERIFIED`.
   - The verification report confirming clean in-memory application, valid Python AST syntax, original issue resolution, and zero introduced findings.
5. **Concurrent Execution Timeline:**
   Show the timeline table demonstrating that `diff_agent`, `style_agent`, `security_agent`, and `test_coverage_agent` ran concurrently before the fan-in barrier.

---

## Step 3: Demonstrate Fault Injection & Graceful Degradation (60 seconds)

Simulate a complete crash of the Security Agent:

```bash
python -m cli.main review --diff samples/diffs/02_sql_injection_and_secret.diff --simulate-failure security
```

### What to highlight:
- The terminal displays: `Simulated fault injection failure triggered for security_agent`.
- In the **Agent Execution Report**, `security_agent` shows status `🔴 failed`.
- **System Resilience:** The pipeline does **not** crash. The Reviewer Manager consolidates findings from the healthy agents (Style and Test-Coverage) and still produces a valid review decision (`REQUEST_CHANGES` due to untested functions).

---

## Step 4: Verify Grounded Retrieval Citations (45 seconds)

Inspect the evidence citation on findings in `output/05_mixed_realistic/review.md`:

```bash
grep "Evidence Citation" output/05_mixed_realistic/review.md
```

### What to highlight:
- Findings cite canonical rule documentation in the knowledge base (e.g. `security/injection_and_unsafe_apis.md#SEC-CMDI-001`).
- This proves findings are grounded in documented company policy rather than ungrounded heuristics.

---

## Step 5: CI Integration & Exit Codes (45 seconds)

Demonstrate automated CI blocking:

```bash
# Clean diff returns exit code 0
python -m cli.main review --diff samples/diffs/01_clean_change.diff --fail-on-request-changes
echo $?  # Outputs 0

# Risky diff returns exit code 1 to block CI pipeline
python -m cli.main review --diff samples/diffs/02_sql_injection_and_secret.diff --fail-on-request-changes
echo $?  # Outputs 1
```
