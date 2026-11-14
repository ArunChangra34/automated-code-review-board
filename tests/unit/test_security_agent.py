"""Unit tests for SecurityAgent and SecurityPlugin."""

import pytest

from agents.security_agent import SecurityAgent
from core.diff_loader import load_diff_from_file
from core.kernel_factory import create_kernel
from core.models import Severity


@pytest.mark.asyncio
async def test_sql_injection_and_secret_detection():
    """Exit check: verify 02_sql_injection_and_secret.diff yields CRITICAL findings for SQLi and secret."""
    kernel = create_kernel()
    agent = SecurityAgent(kernel=kernel)
    state = load_diff_from_file("samples/diffs/02_sql_injection_and_secret.diff")

    result = await agent.run(state)
    assert result.status == "ok"

    critical_findings = [f for f in result.findings if f.severity == Severity.CRITICAL]
    assert len(critical_findings) >= 2

    rule_ids = {f.rule_id for f in critical_findings}
    # SQL Injection must be detected as CRITICAL
    assert "SEC-SQLI-001" in rule_ids
    # Secret key must be detected as CRITICAL
    assert "SEC-SECRET-001" in rule_ids


@pytest.mark.asyncio
async def test_secrets_are_strictly_redacted():
    """Verify secrets are never output in full in snippets or descriptions."""
    kernel = create_kernel()
    agent = SecurityAgent(kernel=kernel)

    raw_keys = ["AKIAIOSFODNN7EXAMPLE12", "ghp_1234567890abcdefghijklmnopqrstuv"]

    # Check sample 02
    state_02 = load_diff_from_file("samples/diffs/02_sql_injection_and_secret.diff")
    res_02 = await agent.run(state_02)
    for finding in res_02.findings:
        for raw in raw_keys:
            assert raw not in (finding.code_snippet or ""), f"Secret leaked in snippet: {raw}"
            assert raw not in finding.description, f"Secret leaked in description: {raw}"

    # Check sample 05
    state_05 = load_diff_from_file("samples/diffs/05_mixed_realistic.diff")
    res_05 = await agent.run(state_05)
    for finding in res_05.findings:
        for raw in raw_keys:
            assert raw not in (finding.code_snippet or ""), f"Secret leaked in snippet: {raw}"
            assert raw not in finding.description, f"Secret leaked in description: {raw}"


@pytest.mark.asyncio
async def test_mixed_realistic_diff_security_patterns():
    """Verify sample 05 flags subprocess command injection, weak MD5 hash, raw DOM injection, and unpinned dependency."""
    kernel = create_kernel()
    agent = SecurityAgent(kernel=kernel)
    state = load_diff_from_file("samples/diffs/05_mixed_realistic.diff")

    result = await agent.run(state)
    assert result.status == "ok"

    rule_ids = {f.rule_id for f in result.findings}
    assert "SEC-CMDI-001" in rule_ids  # shell=True
    assert "SEC-CRYPTO-001" in rule_ids  # md5
    assert "SEC-XSS-001" in rule_ids  # innerHTML
    assert "SEC-SECRET-002" in rule_ids  # ghp token in app_config
    assert "SEC-CORS-001" in rule_ids  # allow_origins: *
    assert "SEC-DEP-001" in rule_ids  # unpinned dependency in requirements.txt
