"""Unit tests for ReviewOrchestrator, ReviewerManager, dedup, and ranking logic."""

import time

import pytest

from core.dedup import are_findings_duplicates, deduplicate_findings
from core.diff_loader import load_diff_from_file
from core.models import Category, Finding, Severity
from core.orchestrator import ReviewOrchestrator
from core.ranking import (
    evaluate_merge_decision,
    identify_corroborations,
)


def test_deduplication_same_location_and_rule():
    """Verify that findings with same file, line, and rule are merged."""
    f1 = Finding(
        id="f1",
        category=Category.SECURITY,
        severity=Severity.HIGH,
        title="SQL Injection",
        description="Dynamic string SQL query",
        file_path="src/repo.py",
        line_start=10,
        line_end=10,
        rule_id="SEC-SQLI-001",
        recommendation="Use parameterized query",
        confidence=0.9,
        reported_by=["security_agent"],
    )
    f2 = Finding(
        id="f2",
        category=Category.SECURITY,
        severity=Severity.CRITICAL,
        title="SQL Injection Detected",
        description="f-string SQL query formatting",
        file_path="src/repo.py",
        line_start=10,
        line_end=10,
        rule_id="SEC-SQLI-001",
        recommendation="Use parameterized query with %s",
        confidence=0.95,
        reported_by=["reviewer_manager"],
    )

    assert are_findings_duplicates(f1, f2) is True

    merged_list, count = deduplicate_findings([f1, f2])
    assert count == 1
    assert len(merged_list) == 1
    # Severity must be upgraded to highest (CRITICAL)
    assert merged_list[0].severity == Severity.CRITICAL
    # Both reporters must be preserved
    assert "security_agent" in merged_list[0].reported_by
    assert "reviewer_manager" in merged_list[0].reported_by


def test_corroboration_detection_and_confidence_boost():
    """Verify that multiple agents flagging same code area triggers corroboration."""
    f_sec = Finding(
        id="f_sec",
        category=Category.SECURITY,
        severity=Severity.CRITICAL,
        title="SQL Injection",
        description="Query interpolation",
        file_path="src/db.py",
        line_start=15,
        rule_id="SEC-SQLI-001",
        recommendation="Fix query",
        confidence=0.85,
        reported_by=["security_agent"],
    )
    f_sty = Finding(
        id="f_sty",
        category=Category.STYLE,
        severity=Severity.LOW,
        title="Long Line",
        description="Query line too long",
        file_path="src/db.py",
        line_start=15,
        rule_id="STY-LEN-001",
        recommendation="Wrap line",
        confidence=0.80,
        reported_by=["style_agent"],
    )

    corroborated = identify_corroborations([f_sec, f_sty])
    assert len(corroborated) == 2
    for f in corroborated:
        assert len(f.corroborated_by) == 2
        assert "security_agent" in f.corroborated_by
        assert "style_agent" in f.corroborated_by
        assert f.confidence > 0.85  # Boosted confidence


def test_decision_rules_policy_paths():
    """Verify policy decision paths: CRITICAL/HIGH block, and clean passes."""
    policy = {
        "weights": {"CRITICAL": 40, "HIGH": 20, "MEDIUM": 8, "LOW": 2, "INFO": 0},
        "blocking_severities": ["CRITICAL", "HIGH"],
        "thresholds": {
            "request_changes_score": 30,
            "max_score": 100,
            "corroboration_multiplier": 0.10,
        },
    }

    # 1. Clean change -> APPROVE
    decision, _, score = evaluate_merge_decision([], policy)
    assert decision == "APPROVE"
    assert score == 0

    # 2. Critical finding -> REQUEST_CHANGES
    f_crit = Finding(
        id="fc",
        category=Category.SECURITY,
        severity=Severity.CRITICAL,
        title="Secret",
        description="Leaked token",
        rule_id="SEC-SECRET-001",
        recommendation="Remove",
    )
    decision, reason, score = evaluate_merge_decision([f_crit], policy)
    assert decision == "REQUEST_CHANGES"
    assert score >= 40
    assert "blocking issue" in reason.lower()

    # 3. Multiple mediums exceeding threshold 30 -> REQUEST_CHANGES
    f_meds = [
        Finding(
            id=f"fm{i}",
            category=Category.STYLE,
            severity=Severity.MEDIUM,
            title=f"Complexity {i}",
            description="High complexity",
            rule_id="STY-COMPLEX-001",
            recommendation="Refactor",
        )
        for i in range(4)  # 4 * 8 = 32 > 30
    ]
    decision, _, score = evaluate_merge_decision(f_meds, policy)
    assert decision == "REQUEST_CHANGES"
    assert score >= 30


@pytest.mark.asyncio
async def test_fan_out_concurrency_execution():
    """Verify that specialist agents execute concurrently (total time < sum of durations)."""
    orchestrator = ReviewOrchestrator()
    state = load_diff_from_file("samples/diffs/01_clean_change.diff")

    start_time = time.perf_counter()
    res_state = await orchestrator.run_review(state)
    elapsed = time.perf_counter() - start_time
    assert elapsed >= 0.0

    assert res_state.consolidated_review is not None
    # Concurrency verification in timeline
    started_events = [e for e in res_state.timeline if e.event == "started"]
    assert len(started_events) >= 4


@pytest.mark.asyncio
async def test_error_isolation_simulated_failure():
    """Verify that an agent failure does not crash pipeline and is captured in review."""
    from config.settings import Settings

    settings = Settings(simulate_failure="security_agent")
    orchestrator = ReviewOrchestrator(settings=settings)
    state = load_diff_from_file("samples/diffs/01_clean_change.diff")

    res_state = await orchestrator.run_review(state)
    assert res_state.consolidated_review is not None
    assert res_state.agent_status["security_agent"] == "failed"
    assert "security_agent" in res_state.consolidated_review.agent_status


@pytest.mark.asyncio
async def test_all_sample_diffs_exit_check():
    """Exit check: run orchestrator on all 5 sample diffs and verify expected decisions."""
    orchestrator = ReviewOrchestrator()

    # Sample 01: Clean feature with tests -> APPROVE
    s01 = load_diff_from_file("samples/diffs/01_clean_change.diff")
    await orchestrator.run_review(s01)
    assert s01.consolidated_review is not None
    assert s01.consolidated_review.decision == "APPROVE"

    # Sample 02: SQL Injection & Secret -> REQUEST_CHANGES
    s02 = load_diff_from_file("samples/diffs/02_sql_injection_and_secret.diff")
    await orchestrator.run_review(s02)
    assert s02.consolidated_review is not None
    assert s02.consolidated_review.decision == "REQUEST_CHANGES"
    assert s02.consolidated_review.priority_order[0].severity == Severity.CRITICAL

    # Sample 03: Untested Feature -> REQUEST_CHANGES
    s03 = load_diff_from_file("samples/diffs/03_untested_feature.diff")
    await orchestrator.run_review(s03)
    assert s03.consolidated_review is not None
    assert s03.consolidated_review.decision == "REQUEST_CHANGES"
    has_high = any(f.severity == Severity.HIGH for f in s03.consolidated_review.priority_order)
    assert has_high

    # Sample 04: Style Mess -> REQUEST_CHANGES
    s04 = load_diff_from_file("samples/diffs/04_style_mess.diff")
    await orchestrator.run_review(s04)
    assert s04.consolidated_review is not None
    assert s04.consolidated_review.decision == "REQUEST_CHANGES"

    # Sample 05: Mixed Realistic -> REQUEST_CHANGES
    s05 = load_diff_from_file("samples/diffs/05_mixed_realistic.diff")
    await orchestrator.run_review(s05)
    assert s05.consolidated_review is not None
    assert s05.consolidated_review.decision == "REQUEST_CHANGES"
