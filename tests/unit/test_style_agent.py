"""Unit tests for StyleAgent and StylePlugin."""

import pytest

from agents.style_agent import StyleAgent
from core.diff_loader import load_diff_from_file
from core.kernel_factory import create_kernel
from core.models import Severity


@pytest.mark.asyncio
async def test_clean_change_has_no_blocking_style_findings():
    """Verify 01_clean_change.diff yields no style findings above INFO."""
    kernel = create_kernel()
    agent = StyleAgent(kernel=kernel)
    state = load_diff_from_file("samples/diffs/01_clean_change.diff")

    result = await agent.run(state)
    assert result.status == "ok"
    high_medium_findings = [
        f
        for f in result.findings
        if f.severity in (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM)
    ]
    assert len(high_medium_findings) == 0


@pytest.mark.asyncio
async def test_style_mess_diff_detects_multiple_violations():
    """Verify 04_style_mess.diff flags naming, bare except, long lines, debug prints, and dead code."""
    kernel = create_kernel()
    agent = StyleAgent(kernel=kernel)
    state = load_diff_from_file("samples/diffs/04_style_mess.diff")

    result = await agent.run(state)
    assert result.status == "ok"
    assert len(result.findings) >= 5

    rule_ids = {f.rule_id for f in result.findings}
    # Must flag line length
    assert "STY-LEN-001" in rule_ids
    # Must flag function naming (PROCESS_USER_RECORDS)
    assert "STY-NAME-001" in rule_ids
    # Must flag class naming (my_custom_handler)
    assert "STY-NAME-002" in rule_ids
    # Must flag bare except
    assert "STY-EXCEPT-001" in rule_ids
    # Must flag wildcard import
    assert "STY-IMPORT-001" in rule_ids
    # Must flag debug print
    assert "STY-DEBUG-001" in rule_ids
    # Must flag commented-out code
    assert "STY-DEAD-001" in rule_ids

    # Verify that all findings have evidence citations attached from knowledge base
    for f in result.findings:
        assert (
            f.evidence_source is not None
        ), f"Finding {f.rule_id} is missing knowledge base grounding"
        assert "style/" in f.evidence_source or "#" in f.evidence_source


@pytest.mark.asyncio
async def test_javascript_style_checks():
    """Verify JavaScript camelCase and console logging checks on sample 05."""
    kernel = create_kernel()
    agent = StyleAgent(kernel=kernel)
    state = load_diff_from_file("samples/diffs/05_mixed_realistic.diff")

    result = await agent.run(state)
    assert result.status == "ok"

    rule_ids = {f.rule_id for f in result.findings}
    # Flags console.log in helpers.js
    assert "STY-DEBUG-002" in rule_ids
    # Flags PascalCase function CalculateDiscount in helpers.js
    assert "STY-NAME-004" in rule_ids
