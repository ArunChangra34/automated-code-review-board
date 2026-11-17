"""Unit and integration tests for the mode-dependent fix suggestions feature."""

import pytest

from config.settings import Settings
from core.diff_loader import load_diff_from_file, load_diff_from_stdin
from core.models import Category, Finding, FixSuggestion, Severity
from core.orchestrator import ReviewOrchestrator, should_suggest_fixes
from core.patch_tools import verify_patch
from reporting.markdown_report import generate_markdown_report


@pytest.mark.asyncio
async def test_offline_auto_mode_produces_no_fixes():
    """In offline + auto mode (default): no suggested_patch, empty fix_suggestions, fix agent not run."""
    settings = Settings(mode="offline", fix_suggestions="auto")
    assert should_suggest_fixes(settings) is False

    state = load_diff_from_file("samples/diffs/02_sql_injection_and_secret.diff")
    orchestrator = ReviewOrchestrator(settings=settings)
    state = await orchestrator.run_review(state)

    assert state.consolidated_review is not None
    assert state.consolidated_review.decision == "REQUEST_CHANGES"
    assert state.suggested_patch is None
    assert state.fix_suggestions == []
    assert "fix_suggestion_agent" not in state.agent_results


@pytest.mark.asyncio
async def test_offline_always_mode_produces_rank1_template_patch_only():
    """In offline + always mode: only the template patch for rank-1 finding runs and verifies."""
    settings = Settings(mode="offline", fix_suggestions="always")
    assert should_suggest_fixes(settings) is True

    state = load_diff_from_file("samples/diffs/02_sql_injection_and_secret.diff")
    orchestrator = ReviewOrchestrator(settings=settings)
    state = await orchestrator.run_review(state)

    assert state.suggested_patch is not None
    assert state.suggested_patch.verification is not None
    assert state.suggested_patch.verification.verdict == "VERIFIED"
    assert state.fix_suggestions == []
    assert "fix_suggestion_agent" in state.agent_results


def test_mode_llm_without_key_effective_offline():
    """Requesting mode=llm without an API key makes effective_mode='offline' and llm_enabled=False."""
    settings = Settings(mode="llm", llm_api_key=None, fix_suggestions="auto")
    assert settings.llm_enabled is False
    assert settings.effective_mode == "offline"
    assert should_suggest_fixes(settings) is False


@pytest.mark.asyncio
async def test_llm_mocked_valid_replace_suggestion_verified():
    """In LLM mode with a valid replacement response, suggestion is produced with real line numbers and VERIFIED."""
    settings = Settings(mode="llm", llm_api_key="sk-mock-valid-key", fix_suggestions="auto")
    assert settings.llm_enabled is True
    assert should_suggest_fixes(settings) is True

    diff_text = """diff --git a/src/db.py b/src/db.py
--- a/src/db.py
+++ b/src/db.py
@@ -1,1 +1,4 @@
+import os
+query = f"SELECT id FROM users WHERE id = {user_id}"
+cursor.execute(query)
"""
    state = load_diff_from_stdin(diff_text)
    orchestrator = ReviewOrchestrator(settings=settings)

    # Mock _call_llm on the orchestrator's fix_agent
    async def mock_call_llm(prompt: str) -> str:
        return """{
            "kind": "replace",
            "file_path": "src/db.py",
            "start_line": 2,
            "end_line": 3,
            "replacement_lines": [
                "query = \\"SELECT id FROM users WHERE id = %s\\"",
                "cursor.execute(query, (user_id,))"
            ],
            "explanation": "Parameterize query using %s placeholders.",
            "new_imports": [],
            "followups": []
        }"""

    orchestrator.fix_agent._call_llm = mock_call_llm

    state = await orchestrator.run_review(state)
    assert len(state.fix_suggestions) >= 1
    sug = state.fix_suggestions[0]
    assert sug.kind == "replace"
    assert sug.source == "llm"
    assert "--- a/src/db.py" in sug.unified_diff
    assert "@@ -2,2 +2,2 @@" in sug.unified_diff
    assert sug.verification is not None
    assert sug.verification.verdict == "VERIFIED"


@pytest.mark.asyncio
async def test_llm_mocked_invalid_json_downgrades_to_manual_guidance():
    """If LLM returns invalid JSON twice, suggestion downgrades to manual guidance and review completes."""
    settings = Settings(mode="llm", llm_api_key="sk-mock-key", fix_suggestions="auto")
    diff_text = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,1 +1,2 @@
+x = 1
+except: pass
"""
    state = load_diff_from_stdin(diff_text)
    orchestrator = ReviewOrchestrator(settings=settings)

    async def mock_bad_json(prompt: str) -> str:
        return "This is completely invalid and not JSON at all."

    orchestrator.fix_agent._call_llm = mock_bad_json

    state = await orchestrator.run_review(state)
    assert state.consolidated_review is not None
    assert len(state.fix_suggestions) >= 1
    sug = state.fix_suggestions[0]
    assert sug.kind == "manual"
    assert "manual guidance" in sug.note


@pytest.mark.asyncio
async def test_llm_mocked_vulnerable_or_broken_patch_rejected():
    """If the LLM suggests a replacement that fails verification, diff is cleared and marked rejected."""
    settings = Settings(mode="llm", llm_api_key="sk-mock-key", fix_suggestions="auto")
    diff_text = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,1 +1,3 @@
+import os
+query = f"SELECT * FROM items WHERE id = {item_id}"
"""
    state = load_diff_from_stdin(diff_text)
    orchestrator = ReviewOrchestrator(settings=settings)

    # Replacement still keeps SQL injection
    async def mock_still_vulnerable(prompt: str) -> str:
        return """{
            "kind": "replace",
            "file_path": "src/app.py",
            "start_line": 2,
            "end_line": 2,
            "replacement_lines": [
                "query = f\\"SELECT * FROM items WHERE id = {item_id}\\""
            ],
            "explanation": "No actual fix.",
            "new_imports": [],
            "followups": []
        }"""

    orchestrator.fix_agent._call_llm = mock_still_vulnerable

    state = await orchestrator.run_review(state)
    assert len(state.fix_suggestions) >= 1
    sug = state.fix_suggestions[0]
    assert sug.kind == "manual"
    assert sug.unified_diff == ""
    assert "rejected:" in sug.note


@pytest.mark.asyncio
async def test_llm_replacement_touching_lines_not_in_diff_downgrades():
    """If LLM replacement lines are outside the diff's added lines, downgrade to manual guidance."""
    settings = Settings(mode="llm", llm_api_key="sk-mock-key", fix_suggestions="auto")
    diff_text = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,1 +1,3 @@
+import os
+query = f"SELECT id FROM users WHERE id = {user_id}"
"""
    state = load_diff_from_stdin(diff_text)
    orchestrator = ReviewOrchestrator(settings=settings)

    # Line 999 is not in added lines
    async def mock_outside_lines(prompt: str) -> str:
        return """{
            "kind": "replace",
            "file_path": "src/app.py",
            "start_line": 999,
            "end_line": 1000,
            "replacement_lines": ["pass"],
            "explanation": "Out of bounds.",
            "new_imports": [],
            "followups": []
        }"""

    orchestrator.fix_agent._call_llm = mock_outside_lines

    state = await orchestrator.run_review(state)
    assert len(state.fix_suggestions) >= 1
    sug = state.fix_suggestions[0]
    assert sug.kind == "manual"
    assert "not all in added-lines" in sug.note


@pytest.mark.asyncio
async def test_llm_new_file_test_suggestion():
    """A new_file suggestion is produced with /dev/null diff, syntax checked, and verification None."""
    settings = Settings(mode="llm", llm_api_key="sk-mock-key", fix_suggestions="auto")
    diff_text = """diff --git a/src/logic.py b/src/logic.py
--- a/src/logic.py
+++ b/src/logic.py
@@ -1,1 +1,3 @@
+def compute_total(a, b):
+    return a + b
"""
    state = load_diff_from_stdin(diff_text)
    orchestrator = ReviewOrchestrator(settings=settings)

    async def mock_new_file(prompt: str) -> str:
        return """{
            "kind": "new_file",
            "file_path": "tests/test_logic.py",
            "content": "def test_compute():\\n    assert True\\n",
            "explanation": "Add unit test for compute_total."
        }"""

    orchestrator.fix_agent._call_llm = mock_new_file

    state = await orchestrator.run_review(state)
    assert len(state.fix_suggestions) >= 1
    sug = state.fix_suggestions[0]
    assert sug.kind == "new_file"
    assert "--- /dev/null" in sug.unified_diff
    assert "+++ b/tests/test_logic.py" in sug.unified_diff
    assert sug.verification is None
    assert "syntax-checked only" in sug.note


@pytest.mark.asyncio
async def test_llm_one_call_fails_others_succeed():
    """One LLM call failing does not prevent other suggestions from succeeding."""
    settings = Settings(mode="llm", llm_api_key="sk-mock-key", fix_suggestions="auto")
    # Sample 02 has multiple eligible findings
    state = load_diff_from_file("samples/diffs/02_sql_injection_and_secret.diff")
    orchestrator = ReviewOrchestrator(settings=settings)

    call_count = 0

    async def mock_partial_fail(prompt: str) -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("API Timeout on first call")
        return """{
            "kind": "manual",
            "explanation": "Manual guidance for this finding."
        }"""

    orchestrator.fix_agent._call_llm = mock_partial_fail

    state = await orchestrator.run_review(state)
    # The agent should still succeed or complete
    assert state.agent_results["fix_suggestion_agent"].status in ("ok", "degraded")
    # Suggestions were recorded for the calls that didn't raise
    assert len(state.fix_suggestions) >= 1


@pytest.mark.asyncio
async def test_llm_all_calls_fail_marks_agent_degraded():
    """If every LLM fix call raises an unhandled error, the agent is marked 'degraded'."""
    settings = Settings(mode="llm", llm_api_key="sk-mock-key", fix_suggestions="auto")
    state = load_diff_from_file("samples/diffs/02_sql_injection_and_secret.diff")
    orchestrator = ReviewOrchestrator(settings=settings)

    async def mock_all_fail(prompt: str) -> str:
        raise ConnectionError("Server unavailable")

    orchestrator.fix_agent._call_llm = mock_all_fail

    state = await orchestrator.run_review(state)
    assert state.consolidated_review is not None
    res = state.agent_results["fix_suggestion_agent"]
    assert res.status == "degraded"
    assert state.fix_suggestions == []


def test_multi_fix_count_based_verifier_not_falsely_rejected():
    """When a file has multiple findings of the same rule, fixing one decreases the count and resolves."""
    original_code = (
        "def func_a():\n"
        "    try:\n"
        "        pass\n"
        "    except:\n"
        "        pass\n"
        "def func_b():\n"
        "    try:\n"
        "        pass\n"
        "    except:\n"
        "        pass\n"
    )

    finding = Finding(
        id="f-bare-except-1",
        category=Category.STYLE,
        severity=Severity.MEDIUM,
        title="Bare Except",
        description="Bare except",
        file_path="app.py",
        line_start=4,
        rule_id="STY-EXCEPT-001",
        recommendation="Catch Exception",
    )

    # Patch that fixes only the first bare except
    patch_text = (
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ -4,1 +4,1 @@\n"
        "-    except:\n"
        "+    except Exception as err:\n"
    )

    verif = verify_patch(
        finding=finding,
        original_content=original_code,
        patch_text=patch_text,
        language="python",
        file_path="app.py",
    )

    # Count of STY-EXCEPT-001 decreased from 2 to 1 -> original_finding_resolved must be True!
    assert verif.original_finding_resolved is True
    assert verif.verdict in ("VERIFIED", "PARTIAL")


@pytest.mark.asyncio
async def test_decision_and_score_identical_with_and_without_fixes():
    """The merge decision, risk score, and ranking are identical with and without fix suggestions."""
    diff_file = "samples/diffs/05_mixed_realistic.diff"

    # Run 1: without fix suggestions (offline, auto)
    s1 = Settings(mode="offline", fix_suggestions="auto")
    state1 = load_diff_from_file(diff_file)
    orch1 = ReviewOrchestrator(settings=s1)
    state1 = await orch1.run_review(state1)

    # Run 2: with fix suggestions (offline, always)
    s2 = Settings(mode="offline", fix_suggestions="always")
    state2 = load_diff_from_file(diff_file)
    orch2 = ReviewOrchestrator(settings=s2)
    state2 = await orch2.run_review(state2)

    assert state1.consolidated_review is not None
    assert state2.consolidated_review is not None
    assert state1.consolidated_review.decision == state2.consolidated_review.decision
    assert (
        state1.consolidated_review.merge_risk_score == state2.consolidated_review.merge_risk_score
    )
    ranks1 = [f.id for f in state1.consolidated_review.priority_order]
    ranks2 = [f.id for f in state2.consolidated_review.priority_order]
    assert ranks1 == ranks2


@pytest.mark.asyncio
async def test_secrets_never_appear_in_call_llm_prompt():
    """Raw secrets must never be passed in the prompt to _call_llm."""
    settings = Settings(mode="llm", llm_api_key="sk-mock-key", fix_suggestions="auto")
    state = load_diff_from_file("samples/diffs/02_sql_injection_and_secret.diff")
    orchestrator = ReviewOrchestrator(settings=settings)

    captured_prompts: list[str] = []

    async def mock_capture(prompt: str) -> str:
        captured_prompts.append(prompt)
        return """{"kind": "manual", "explanation": "Guidance"}"""

    orchestrator.fix_agent._call_llm = mock_capture
    await orchestrator.run_review(state)

    assert len(captured_prompts) > 0
    raw_secret = "AKIAIOSFODNN7EXAMPLE12"
    for p in captured_prompts:
        assert raw_secret not in p, f"Raw secret leaked into prompt: {p}"


@pytest.mark.asyncio
async def test_markdown_report_section_text_in_offline_vs_llm():
    """Verify markdown report section displays correct text in offline mode vs LLM mode."""
    # 1. Offline mode
    s_off = Settings(mode="offline", fix_suggestions="auto")
    state_off = load_diff_from_file("samples/diffs/01_clean_change.diff")
    orch_off = ReviewOrchestrator(settings=s_off)
    state_off = await orch_off.run_review(state_off)

    md_off = generate_markdown_report(state_off, mode="offline")
    assert "## Fix Suggestions (LLM-assisted)" in md_off
    assert "Fix suggestions are available in LLM mode" in md_off

    # 2. LLM mode with suggestions
    s_llm = Settings(mode="llm", llm_api_key="sk-mock-key", fix_suggestions="auto")
    state_llm = load_diff_from_file("samples/diffs/01_clean_change.diff")
    state_llm.fix_suggestions = [
        FixSuggestion(
            finding_id="f-1",
            rule_id="STY-DOC-001",
            severity=Severity.LOW,
            file_path="src/feature.py",
            line_start=5,
            kind="manual",
            source="llm",
            explanation="Add a module docstring.",
            note="manual guidance",
        )
    ]
    md_llm = generate_markdown_report(state_llm, mode=s_llm.effective_mode)
    assert "The following 1 fix suggestion(s) were generated and verified:" in md_llm
    assert "STY-DOC-001" in md_llm
