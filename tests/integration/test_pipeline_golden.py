"""Integration tests running full pipeline on all 5 sample diffs against golden outputs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.diff_loader import load_diff_from_file
from core.orchestrator import ReviewOrchestrator

SAMPLES = [
    "01_clean_change",
    "02_sql_injection_and_secret",
    "03_untested_feature",
    "04_style_mess",
    "05_mixed_realistic",
]


@pytest.mark.parametrize("sample_name", SAMPLES)
@pytest.mark.asyncio
async def test_sample_diff_against_golden_output(sample_name: str) -> None:
    """Validate review decision, severity counts, and top finding against expected golden JSON."""
    diff_path = Path("samples/diffs") / f"{sample_name}.diff"
    expected_path = Path("samples/expected") / f"{sample_name}.json"

    assert diff_path.exists(), f"Diff file not found: {diff_path}"
    assert expected_path.exists(), f"Golden file not found: {expected_path}"

    expected_data = json.loads(expected_path.read_text(encoding="utf-8"))

    state = load_diff_from_file(diff_path)
    orchestrator = ReviewOrchestrator()
    state = await orchestrator.run_review(state)

    review = state.consolidated_review
    assert review is not None

    # 1. Decision check
    assert review.decision == expected_data["decision"], (
        f"Decision mismatch for {sample_name}: got {review.decision}, "
        f"expected {expected_data['decision']}"
    )

    # 2. Risk score within bounds
    assert (
        expected_data["min_risk_score"]
        <= review.merge_risk_score
        <= expected_data["max_risk_score"]
    )

    # 3. Severity counts
    actual_counts = review.stats.get("counts_by_severity", {})
    expected_counts = expected_data.get("counts_by_severity", {})
    for sev, cnt in expected_counts.items():
        assert actual_counts.get(sev, 0) == cnt, (
            f"Severity count mismatch for {sample_name} [{sev}]: "
            f"got {actual_counts.get(sev, 0)}, expected {cnt}"
        )

    # 4. Top finding rule ID
    top_rule = review.priority_order[0].rule_id if review.priority_order else None
    assert top_rule == expected_data["top_rule_id"]

    # 5. Patch verification verdict
    patch = state.suggested_patch or review.suggested_patch
    patch_verdict = patch.verification.verdict if patch and patch.verification else None
    assert patch_verdict == expected_data["patch_verdict"]
