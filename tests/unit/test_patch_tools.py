"""Unit tests for patch tools and Patch Verification Loop."""

from core.models import Category, Finding, Severity
from core.patch_tools import (
    apply_unified_diff_in_memory,
    check_syntax,
    verify_patch,
)


def test_apply_unified_diff_in_memory():
    """Verify clean in-memory application of unified diff patch."""
    orig = """def greet(name):
    return f"Hello, {name}"
"""
    patch = """--- a/greet.py
+++ b/greet.py
@@ -1,2 +1,2 @@
 def greet(name):
-    return f"Hello, {name}"
+    return f"Greetings, {name}!"
"""
    success, res, err = apply_unified_diff_in_memory(orig, patch)
    assert success is True
    assert "Greetings, " in res
    assert "Hello, " not in res


def test_check_syntax_detects_python_errors():
    """Verify syntax checker catches invalid syntax."""
    valid_code = "def foo():\n    return 42\n"
    invalid_code = "def foo(:\n    return 42\n"

    ok1, _ = check_syntax(valid_code, "python")
    assert ok1 is True

    ok2, err2 = check_syntax(invalid_code, "python")
    assert ok2 is False
    assert "SyntaxError" in err2


def test_verify_patch_rejects_broken_patch():
    """Verify verification loop returns REJECTED when patch syntax is broken."""
    orig = "def foo():\n    pass\n"
    broken_patch = """--- a/foo.py
+++ b/foo.py
@@ -1,2 +1,2 @@
 def foo():
-    pass
+    this is invalid python syntax !!!
"""
    finding = Finding(
        id="f1",
        category=Category.STYLE,
        severity=Severity.LOW,
        title="Issue",
        description="Desc",
        rule_id="STY-001",
        recommendation="Fix",
    )
    verification = verify_patch(
        finding=finding,
        original_content=orig,
        patch_text=broken_patch,
        language="python",
        file_path="foo.py",
    )
    assert verification.verdict == "REJECTED"
    assert verification.syntax_ok is False


def test_verify_patch_rejects_still_vulnerable_patch():
    """Verify verification loop returns REJECTED if original vulnerability remains."""
    orig = "def query(user):\n    return f'SELECT * FROM u WHERE id = {user}'\n"
    # Patch replaces quotes but keeps f-string SQL injection!
    vulnerable_patch = """--- a/foo.py
+++ b/foo.py
@@ -1,2 +1,2 @@
 def query(user):
-    return f'SELECT * FROM u WHERE id = {user}'
+    return f"SELECT id, name FROM u WHERE id = {user}"
"""
    finding = Finding(
        id="f1",
        category=Category.SECURITY,
        severity=Severity.CRITICAL,
        title="SQL Injection",
        description="Desc",
        rule_id="SEC-SQLI-001",
        recommendation="Fix",
    )
    verification = verify_patch(
        finding=finding,
        original_content=orig,
        patch_text=vulnerable_patch,
        language="python",
        file_path="foo.py",
    )
    assert verification.verdict == "REJECTED"
    assert verification.original_finding_resolved is False


def test_verify_patch_accepts_clean_patch():
    """Verify verification loop returns VERIFIED when patch cleanly resolves issue."""
    orig = """def get_user_by_username(username: str):
    cursor = get_connection().cursor()
    query = f"SELECT id, username, email FROM users WHERE username = '{username}'"
    cursor.execute(query)
    return cursor.fetchone()
"""
    clean_patch = """--- a/src/db/user_repository.py
+++ b/src/db/user_repository.py
@@ -1,5 +1,5 @@
 def get_user_by_username(username: str):
     cursor = get_connection().cursor()
-    query = f"SELECT id, username, email FROM users WHERE username = '{username}'"
-    cursor.execute(query)
+    query = "SELECT id, username, email FROM users WHERE username = %s"
+    cursor.execute(query, (username,))
     return cursor.fetchone()
"""
    finding = Finding(
        id="f1",
        category=Category.SECURITY,
        severity=Severity.CRITICAL,
        title="SQL Injection",
        description="Desc",
        rule_id="SEC-SQLI-001",
        recommendation="Fix",
    )
    verification = verify_patch(
        finding=finding,
        original_content=orig,
        patch_text=clean_patch,
        language="python",
        file_path="src/db/user_repository.py",
    )
    assert verification.verdict == "VERIFIED"
    assert verification.applies_cleanly is True
    assert verification.syntax_ok is True
    assert verification.original_finding_resolved is True
