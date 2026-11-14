"""Unit tests for TestCoverageAgent and CoveragePlugin."""

import pytest

from agents.test_coverage_agent import TestCoverageAgent
from core.diff_loader import load_diff_from_file
from core.kernel_factory import create_kernel
from core.models import Severity


@pytest.mark.asyncio
async def test_clean_change_with_tests_has_no_untested_findings():
    """Verify 01_clean_change.diff (which includes tests) produces no untested findings."""
    kernel = create_kernel()
    agent = TestCoverageAgent(kernel=kernel)
    state = load_diff_from_file("samples/diffs/01_clean_change.diff")

    result = await agent.run(state)
    assert result.status == "ok"

    untested = [f for f in result.findings if f.rule_id == "TST-UNTESTED-001"]
    assert len(untested) == 0

    metrics = agent.last_analysis_metrics
    assert metrics["has_assertions"] is True
    assert metrics["has_error_tests"] is True
    assert metrics["test_ratio"] > 0.5


@pytest.mark.asyncio
async def test_untested_feature_diff_yields_high_severity_findings():
    """Exit check: verify 03_untested_feature.diff yields HIGH untested-logic findings."""
    kernel = create_kernel()
    agent = TestCoverageAgent(kernel=kernel)
    state = load_diff_from_file("samples/diffs/03_untested_feature.diff")

    result = await agent.run(state)
    assert result.status == "ok"

    high_untested = [
        f
        for f in result.findings
        if f.severity == Severity.HIGH and f.rule_id == "TST-UNTESTED-001"
    ]
    assert len(high_untested) >= 2  # DiscountPolicy, calculate_order_total, dispatch_invoice

    symbols_flagged = {f.title for f in high_untested}
    assert any("DiscountPolicy" in s for s in symbols_flagged)
    assert any("calculate_order_total" in s for s in symbols_flagged)

    metrics = agent.last_analysis_metrics
    assert metrics["test_ratio"] == 0.0
    assert metrics["has_assertions"] is False


@pytest.mark.asyncio
async def test_config_only_change_produces_no_coverage_findings():
    """Verify changes without production code files do not produce test coverage findings."""
    from core.diff_loader import parse_diff_text
    from core.state import ChangeState

    config_diff = """--- a/config/app.yaml
+++ b/config/app.yaml
@@ -1,2 +1,3 @@
 env: production
+timeout: 30
"""
    files, change_id = parse_diff_text(config_diff)
    state = ChangeState(change_id=change_id, source="config", raw_diff=config_diff, files=files)

    kernel = create_kernel()
    agent = TestCoverageAgent(kernel=kernel)
    result = await agent.run(state)

    assert result.status == "ok"
    assert len(result.findings) == 0
