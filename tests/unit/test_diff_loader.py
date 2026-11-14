"""Unit tests for diff loader and parser."""

from pathlib import Path

from core.diff_loader import (
    detect_file_role,
    detect_language,
    load_diff_from_file,
    parse_diff_text,
)


def test_language_detection():
    """Verify file extension language mappings."""
    assert detect_language("app/main.py") == "python"
    assert detect_language("web/script.js") == "javascript"
    assert detect_language("web/app.tsx") == "typescript"
    assert detect_language("query.sql") == "sql"
    assert detect_language("unknown.xyz") == "text"


def test_role_detection():
    """Verify file classification rules."""
    assert detect_file_role("tests/test_api.py") == "test"
    assert detect_file_role("src/components/button.spec.js") == "test"
    assert detect_file_role("requirements.txt") == "dependency"
    assert detect_file_role("package.json") == "dependency"
    assert detect_file_role("config/settings.yaml") == "config"
    assert detect_file_role("Dockerfile") == "build"
    assert detect_file_role("docs/index.md") == "docs"
    assert detect_file_role("src/core/models.py") == "source"


def test_empty_diff_parsing():
    """Verify handling of empty or whitespace diff."""
    files, change_id = parse_diff_text("")
    assert files == []
    assert change_id is not None


def test_hunk_and_lines_parsing():
    """Verify line numbers and hunk structure parsing."""
    diff_text = """--- a/src/math.py
+++ b/src/math.py
@@ -1,3 +1,4 @@
 def add(a, b):
-    return 0
+    # sum
+    return a + b
"""
    files, change_id = parse_diff_text(diff_text)
    assert len(files) == 1
    fc = files[0]
    assert fc.path == "src/math.py"
    assert fc.lines_added == 2
    assert fc.lines_removed == 1
    assert len(fc.hunks) == 1
    hunk = fc.hunks[0]
    assert len(hunk.added_lines) == 2
    assert hunk.added_lines[0].line_number == 2
    assert hunk.added_lines[0].content == "    # sum"
    assert hunk.added_lines[1].line_number == 3
    assert hunk.added_lines[1].content == "    return a + b"


def test_all_sample_diffs_load():
    """Verify that every sample diff file loads cleanly into a valid ChangeState."""
    samples_dir = Path("samples/diffs")
    sample_files = list(samples_dir.glob("*.diff"))
    assert len(sample_files) == 5, f"Expected 5 sample diffs, found {len(sample_files)}"

    for diff_path in sample_files:
        state = load_diff_from_file(diff_path)
        assert state.change_id is not None
        assert len(state.files) > 0
        assert len(state.raw_diff) > 0
        # Verify JSON serializability
        dumped = state.model_dump_json()
        assert len(dumped) > 0
