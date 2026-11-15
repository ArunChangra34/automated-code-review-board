"""Unit tests for FixSuggestionAgent and end-to-end patch verification."""

import pytest

from core.diff_loader import load_diff_from_file
from core.orchestrator import ReviewOrchestrator


@pytest.mark.asyncio
async def test_sample_02_generates_verified_patch_for_rank_1_finding():
    """Exit check: sample 02's top finding gets a VERIFIED patch and verification details."""
    orchestrator = ReviewOrchestrator()
    state = load_diff_from_file("samples/diffs/02_sql_injection_and_secret.diff")

    await orchestrator.run_review(state)

    assert state.consolidated_review is not None
    assert state.suggested_patch is not None
    patch = state.suggested_patch

    # Verify patch fields
    assert patch.finding_id is not None
    assert patch.file_path == "src/db/user_repository.py"
    assert len(patch.unified_diff) > 0

    # Verify machine verification result
    assert patch.verification is not None
    assert patch.verification.applies_cleanly is True
    assert patch.verification.syntax_ok is True
    assert patch.verification.original_finding_resolved is True
    assert patch.verification.verdict == "VERIFIED"
