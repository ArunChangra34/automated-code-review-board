"""Unit tests for core models and state management."""

import pytest

from core.models import Category, Finding, Severity
from core.state import AgentResult, ChangeState


def test_severity_ordering():
    """Verify severity ordering and comparison semantics."""
    assert Severity.CRITICAL > Severity.HIGH
    assert Severity.HIGH > Severity.MEDIUM
    assert Severity.MEDIUM > Severity.LOW
    assert Severity.LOW > Severity.INFO

    # Test sorting
    severities = [Severity.LOW, Severity.CRITICAL, Severity.INFO, Severity.HIGH, Severity.MEDIUM]
    sorted_sev = sorted(severities, reverse=True)
    assert sorted_sev == [
        Severity.CRITICAL,
        Severity.HIGH,
        Severity.MEDIUM,
        Severity.LOW,
        Severity.INFO,
    ]


def test_finding_id_stability():
    """Verify that finding ID generation is deterministic and stable."""
    id1 = Finding.generate_id(Category.SECURITY, "SEC-SQLI-001", "src/db.py", 42)
    id2 = Finding.generate_id(Category.SECURITY, "SEC-SQLI-001", "src/db.py", 42)
    id3 = Finding.generate_id(Category.STYLE, "SEC-SQLI-001", "src/db.py", 42)

    assert id1 == id2
    assert id1 != id3


def test_finding_serialization():
    """Verify Finding serialization to dict and JSON."""
    finding = Finding(
        id=Finding.generate_id(Category.SECURITY, "SEC-SQLI-001", "src/db.py", 12),
        category=Category.SECURITY,
        severity=Severity.CRITICAL,
        title="SQL Injection",
        description="Raw string query formatting",
        file_path="src/db.py",
        line_start=12,
        line_end=12,
        rule_id="SEC-SQLI-001",
        recommendation="Use parameterized queries",
        confidence=0.95,
        reported_by=["security_agent"],
    )

    data = finding.model_dump()
    assert data["severity"] == "CRITICAL"
    assert data["rule_id"] == "SEC-SQLI-001"

    json_str = finding.model_dump_json()
    assert "CRITICAL" in json_str
    assert "SEC-SQLI-001" in json_str


@pytest.mark.asyncio
async def test_change_state_aggregation():
    """Verify that ChangeState aggregates findings across agent results."""
    state = ChangeState(
        change_id="test-change",
        source="test.diff",
        raw_diff="--- a\n+++ b",
    )

    finding1 = Finding(
        id="f1",
        category=Category.SECURITY,
        severity=Severity.HIGH,
        title="Issue 1",
        description="Desc 1",
        rule_id="R1",
        recommendation="Rec 1",
        confidence=1.0,
    )
    finding2 = Finding(
        id="f2",
        category=Category.STYLE,
        severity=Severity.LOW,
        title="Issue 2",
        description="Desc 2",
        rule_id="R2",
        recommendation="Rec 2",
        confidence=1.0,
    )

    res1 = AgentResult(
        agent_name="security_agent",
        status="ok",
        findings=[finding1],
        duration_ms=10.5,
    )
    res2 = AgentResult(
        agent_name="style_agent",
        status="ok",
        findings=[finding2],
        duration_ms=8.2,
    )

    await state.record_agent_start("security_agent")
    await state.record_agent_result(res1)
    await state.record_agent_start("style_agent")
    await state.record_agent_result(res2)

    assert len(state.all_findings) == 2
    assert state.agent_status["security_agent"] == "ok"
    assert len(state.timeline) == 4
