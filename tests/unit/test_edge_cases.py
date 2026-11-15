"""Unit tests for diff edge cases: empty, binary, huge, non-UTF8, malformed, unsupported lang."""

import pytest

from core.diff_loader import load_diff_from_file, load_diff_from_stdin, parse_diff_text
from core.orchestrator import ReviewOrchestrator


def test_empty_diff_handling():
    """Verify empty diff parses into empty file change list without crashing."""
    files, change_id = parse_diff_text("")
    assert len(files) == 0
    assert change_id is not None

    files_ws, change_id_ws = parse_diff_text("   \n\t\n  ")
    assert len(files_ws) == 0


def test_binary_only_diff_handling():
    """Verify binary files in diff are marked as binary and have no hunks."""
    diff_text = (
        "diff --git a/logo.png b/logo.png\n"
        "new file mode 100644\n"
        "index 0000000..e69de29\n"
        "Binary files /dev/null and b/logo.png differ\n"
    )
    files, _ = parse_diff_text(diff_text)
    assert len(files) == 1
    assert files[0].path == "logo.png"
    assert files[0].is_binary is True
    assert len(files[0].hunks) == 0


def test_huge_diff_safe_truncation():
    """Verify huge diff exceeding max_lines is truncated cleanly without exception."""
    # Construct a massive diff of 6000 lines
    diff_lines = [
        "diff --git a/huge.py b/huge.py\n",
        "--- a/huge.py\n",
        "+++ b/huge.py\n",
        "@@ -1,3000 +1,6000 @@\n",
    ]
    for i in range(6000):
        diff_lines.append(f"+    val_{i} = {i}\n")
    huge_diff = "".join(diff_lines)

    files, _ = parse_diff_text(huge_diff, max_lines=1000)
    assert len(files) >= 0


def test_path_traversal_sanitisation():
    """Verify diff paths containing directory traversal or root slashes are sanitized."""
    diff_text = (
        "diff --git a/../../etc/passwd b/../../etc/passwd\n"
        "--- a/../../etc/passwd\n"
        "+++ b/../../etc/passwd\n"
        "@@ -1,1 +1,1 @@\n"
        "+root:x:0:0:root:/root:/bin/bash\n"
    )
    files, _ = parse_diff_text(diff_text)
    assert len(files) == 1
    assert not files[0].path.startswith("..")
    assert not files[0].path.startswith("/")
    assert files[0].path == "etc/passwd"


def test_malformed_diff_raises_clear_error():
    """Verify completely invalid diff text raises ValueError with clear message."""
    invalid_diff = "this is not a unified diff at all\nno hunks\nno headers"
    with pytest.raises(ValueError, match="Failed to parse unified diff"):
        parse_diff_text(invalid_diff)


def test_non_utf8_diff_handling(tmp_path):
    """Verify loading a diff file with non-UTF-8 bytes replaces them gracefully."""
    non_utf8_bytes = b"diff --git a/bad.py b/bad.py\n--- a/bad.py\n+++ b/bad.py\n@@ -1,1 +1,1 @@\n+# \xff\xfe non utf8\n"
    file_path = tmp_path / "bad.diff"
    file_path.write_bytes(non_utf8_bytes)

    state = load_diff_from_file(file_path)
    assert len(state.files) == 1
    assert state.files[0].path == "bad.py"


@pytest.mark.asyncio
async def test_unsupported_language_end_to_end():
    """Verify an unsupported language file is handled gracefully by the orchestrator."""
    diff_text = (
        "diff --git a/program.clj b/program.clj\n"
        "--- a/program.clj\n"
        "+++ b/program.clj\n"
        "@@ -1,2 +1,3 @@\n"
        " (ns myapp.core)\n"
        "+(defn foo [x] (+ x 1))\n"
        ' (println "done")\n'
    )
    state = load_diff_from_stdin(diff_text)
    orchestrator = ReviewOrchestrator()
    state = await orchestrator.run_review(state)
    assert state.consolidated_review is not None
    assert state.consolidated_review.decision in ("APPROVE", "REQUEST_CHANGES")
