"""Targeted tests to ensure >= 85% test coverage across core/ and agents/."""

import logging
from unittest.mock import MagicMock

import pytest

from agents.base_agent import BaseAgent
from agents.fix_suggestion_agent import FixSuggestionAgent
from config.settings import Settings
from core.kernel_factory import create_kernel
from core.logging_setup import SafeFormatter, configure_logging, redact_secrets_in_text
from core.models import Category, Finding, Severity
from core.patch_tools import apply_unified_diff_in_memory, check_syntax
from core.state import ChangeState


def test_severity_comparison_operators():
    """Verify all comparison operators on Severity enum."""
    assert Severity.INFO <= Severity.LOW
    assert Severity.LOW <= Severity.LOW
    assert Severity.CRITICAL >= Severity.HIGH
    assert Severity.HIGH >= Severity.HIGH
    assert Severity.HIGH > Severity.MEDIUM
    assert Severity.MEDIUM < Severity.CRITICAL


def test_logging_redaction_and_formatter():
    """Verify secret redaction and safe formatter."""
    text_with_secret = 'api_key="1234567890abcdef" and password="secretpass123"'
    redacted = redact_secrets_in_text(text_with_secret)
    assert "1234567890abcdef" not in redacted
    assert "secretpass123" not in redacted

    logger = logging.getLogger("test_safe_formatter")
    record = logger.makeRecord("test", logging.INFO, "test.py", 10, text_with_secret, (), None)
    setattr(record, "change_id", "ch-1234")
    formatter = SafeFormatter()
    formatted = formatter.format(record)
    assert "[ch-1234]" in formatted
    assert "1234567890abcdef" not in formatted

    # Test configure_logging
    configure_logging("DEBUG")
    assert logging.getLogger().level == logging.DEBUG


def test_patch_tools_syntax_and_apply():
    """Verify syntax checking on Python, JSON, and YAML formats, and in-memory diff apply."""
    # Python
    ok, _ = check_syntax("x = 1\n", "python")
    assert ok is True
    ok, err = check_syntax("def bad(:\n", "python")
    assert ok is False
    assert "SyntaxError" in err

    # JSON
    ok, _ = check_syntax('{"key": "value"}', "json")
    assert ok is True
    ok, _ = check_syntax('{"key": unquoted}', "json")
    assert ok is False

    # YAML
    ok, _ = check_syntax("key: value\nlist:\n  - 1", "yaml")
    assert ok is True
    ok, _ = check_syntax("key: [unclosed", "yaml")
    assert ok is False

    # Other / unknown language
    ok, _ = check_syntax("plain text", "unknown")
    assert ok is True

    # Empty patch
    ok, _, err = apply_unified_diff_in_memory("x = 1", "")
    assert ok is False

    # Malformed patch
    ok, _, err = apply_unified_diff_in_memory("x = 1", "not a patch")
    assert ok is False


@pytest.mark.asyncio
async def test_fix_suggestion_sqli_template():
    """Verify fix suggestion template generates parameterised query patch for SEC-SQLI-001."""
    finding = Finding(
        id="f-sqli",
        category=Category.SECURITY,
        severity=Severity.CRITICAL,
        title="SQL Injection",
        description="SQL injection in cursor.execute",
        file_path="app/db.py",
        line_start=3,
        code_snippet='query = f"SELECT * FROM users WHERE name = {user_input}"\ncursor.execute(query)',
        rule_id="SEC-SQLI-001",
        recommendation="Use parameterised queries.",
    )
    raw_content = (
        "def find_user(user_input):\n"
        '    query = f"SELECT * FROM users WHERE name = {user_input}"\n'
        "    cursor.execute(query)\n"
    )

    fix_agent = FixSuggestionAgent(kernel=create_kernel())
    patch_text, explanation, imports, followups = fix_agent.generate_template_patch(
        finding, "app/db.py", raw_content
    )
    assert patch_text is not None
    assert "WHERE name = %s" in patch_text
    assert "cursor.execute(query, (user_input,))" in patch_text
    assert "parameterize" in explanation.lower()


@pytest.mark.asyncio
async def test_fix_suggestion_bare_except_template():
    """Verify fix suggestion template replaces bare except with except Exception."""
    finding = Finding(
        id="f-except",
        category=Category.STYLE,
        severity=Severity.MEDIUM,
        title="Bare Except",
        description="Do not use bare except clause",
        file_path="app/util.py",
        line_start=3,
        code_snippet="except:",
        rule_id="STY-EXCEPT-001",
        recommendation="Catch specific exceptions or Exception.",
    )
    raw_content = "try:\n    do_something()\nexcept:\n    pass\n"

    fix_agent = FixSuggestionAgent(kernel=create_kernel())
    patch_text, explanation, imports, followups = fix_agent.generate_template_patch(
        finding, "app/util.py", raw_content
    )
    assert patch_text is not None
    assert "except Exception as err:" in patch_text


@pytest.mark.asyncio
async def test_base_agent_llm_augmentation_flow():
    """Verify BaseAgent LLM augmentation and JSON schema parsing."""
    settings = Settings(mode="llm", llm_provider="openai", llm_api_key="sk-test-mock-key")
    kernel = create_kernel(settings)

    class DummySpecialist(BaseAgent):
        async def analyze_deterministic(self, state: ChangeState) -> list[Finding]:
            return [
                Finding(
                    id="base-1",
                    category=Category.SECURITY,
                    severity=Severity.HIGH,
                    title="Base Issue",
                    description="Base desc",
                    rule_id="SEC-TEST-001",
                    recommendation="Fix it",
                )
            ]

    agent = DummySpecialist(
        name="dummy_specialist",
        description="Testing LLM flow",
        instructions="Test",
        category=Category.SECURITY,
        kernel=kernel,
        settings=settings,
    )

    # Mock SK agent invoke to yield valid JSON list async generator
    fake_response = MagicMock()
    fake_response.content = (
        '[{"title": "Augmented Title", "severity": "HIGH", "rule_id": "SEC-TEST-001", '
        '"description": "Augmented explanation", "recommendation": "Review code"}]'
    )

    async def fake_invoke(*args, **kwargs):
        yield fake_response

    agent.sk_agent = MagicMock()
    agent.sk_agent.invoke = fake_invoke

    state = ChangeState(
        change_id="llm-test",
        source="diff",
        raw_diff="diff --git a/a.py b/a.py\n+x = 1\n",
    )

    result = await agent.run(state)
    assert result.status == "ok"
    assert result.mode == "llm"
    assert len(result.findings) == 2
    assert result.findings[1].title == "Augmented Title"
