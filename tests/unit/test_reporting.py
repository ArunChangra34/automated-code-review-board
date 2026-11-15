"""Unit tests for reporting modules (markdown, JSON, console)."""

from pathlib import Path

import pytest

from core.diff_loader import load_diff_from_file
from core.orchestrator import ReviewOrchestrator
from reporting.json_report import generate_json_report
from reporting.markdown_report import generate_markdown_report


@pytest.mark.asyncio
async def test_markdown_report_sections():
    """Verify that generated markdown contains all required sections from spec §10."""
    diff_path = Path("samples/diffs/02_sql_injection_and_secret.diff")
    state = load_diff_from_file(diff_path)
    orchestrator = ReviewOrchestrator()
    state = await orchestrator.run_review(state)

    md = generate_markdown_report(state, mode="offline")

    # Check required section headers
    assert "# Automated Code Review Board Report" in md
    assert "## Merge Recommendation" in md
    assert "## Change Summary" in md
    assert "## Findings by Severity" in md
    assert "## Priority Order (Fix First)" in md
    assert "## Test Coverage Map" in md
    assert "## Suggested Fix for Top Finding" in md
    assert "## Agent Execution Report" in md
    assert "## Statistics" in md

    # Check key content
    assert "RECOMMENDATION: REQUEST CHANGES" in md
    assert "CRITICAL" in md
    assert "SEC-SQLI-001" in md or "SEC-SECRET-001" in md
    assert "VERIFIED" in md


@pytest.mark.asyncio
async def test_json_report_structure():
    """Verify JSON report serializes full review snapshot with change_id and consolidated review."""
    diff_path = Path("samples/diffs/01_clean_change.diff")
    state = load_diff_from_file(diff_path)
    orchestrator = ReviewOrchestrator()
    state = await orchestrator.run_review(state)

    json_str = generate_json_report(state)
    import json

    data = json.loads(json_str)

    assert data["change_id"] == state.change_id
    assert data["source"] == str(diff_path)
    assert data["consolidated_review"]["decision"] == "APPROVE"
    assert "agent_results" in data
    assert "timeline" in data
