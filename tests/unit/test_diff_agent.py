"""Unit tests for DiffAgent and DiffPlugin."""

from pathlib import Path

import pytest

from agents.diff_agent import DiffAgent
from core.diff_loader import load_diff_from_file
from core.kernel_factory import create_kernel
from plugins.diff_plugin import DiffPlugin


@pytest.mark.asyncio
async def test_diff_plugin_symbol_extraction():
    """Verify function and class symbol extraction from added lines."""
    plugin = DiffPlugin()
    state = load_diff_from_file("samples/diffs/01_clean_change.diff")
    symbols = plugin.extract_symbols(state.files)

    assert "calculate_hypotenuse" in symbols
    assert "test_calculate_hypotenuse_valid" in symbols


@pytest.mark.asyncio
async def test_diff_plugin_risk_area_detection():
    """Verify detection of sensitive domains (database, auth, etc.)."""
    kernel = create_kernel()
    agent = DiffAgent(kernel=kernel)

    # Sample 02 touches database and auth/secret
    state_02 = load_diff_from_file("samples/diffs/02_sql_injection_and_secret.diff")
    await agent.run(state_02)
    assert state_02.summary is not None
    assert "database" in state_02.summary.risk_areas or "auth" in state_02.summary.risk_areas

    # Sample 05 touches auth, crypto, subprocess
    state_05 = load_diff_from_file("samples/diffs/05_mixed_realistic.diff")
    await agent.run(state_05)
    assert state_05.summary is not None
    assert "crypto" in state_05.summary.risk_areas
    assert "subprocess" in state_05.summary.risk_areas


@pytest.mark.asyncio
async def test_all_sample_diffs_yield_change_summary():
    """Exit check: verify every sample diff yields a complete, valid ChangeSummary."""
    kernel = create_kernel()
    agent = DiffAgent(kernel=kernel)

    sample_diffs = sorted(Path("samples/diffs").glob("*.diff"))
    assert len(sample_diffs) == 5

    for diff_path in sample_diffs:
        state = load_diff_from_file(diff_path)
        result = await agent.run(state)

        assert result.status == "ok"
        assert state.summary is not None
        assert state.summary.total_files > 0
        assert state.summary.lines_added > 0
        assert state.summary.size_class in ("XS", "S", "M", "L", "XL")
        assert len(state.summary.intent_summary) > 10
