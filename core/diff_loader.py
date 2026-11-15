"""Diff loading and parsing module converting diffs into structured ChangeState."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Literal

from unidiff import PatchSet
from unidiff.errors import UnidiffParseError

from core.logging_setup import get_logger
from core.models import FileChange, HunkInfo, LineInfo
from core.state import ChangeState

logger = get_logger("diff_loader")

_LANGUAGE_BY_EXT = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".rb": "ruby",
    ".php": "php",
    ".sh": "bash",
    ".bash": "bash",
    ".sql": "sql",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "css",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".md": "markdown",
    ".rst": "markdown",
}

_DEPENDENCY_FILES = {
    "requirements.txt",
    "pipfile",
    "pipfile.lock",
    "pyproject.toml",
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "cargo.toml",
    "cargo.lock",
    "pom.xml",
    "build.gradle",
    "gemfile",
    "gemfile.lock",
}

_BUILD_FILES = {
    "makefile",
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "jenkinsfile",
}


def detect_language(file_path: str) -> str:
    """Detect programming or markup language from file extension."""
    suffix = Path(file_path).suffix.lower()
    return _LANGUAGE_BY_EXT.get(suffix, "text")


def detect_file_role(
    file_path: str,
) -> Literal["source", "test", "config", "docs", "dependency", "build", "other"]:
    """Classify the functional role of a file in the codebase."""
    path_lower = file_path.lower()
    file_name = Path(file_path).name.lower()

    # Test file patterns
    if (
        "test" in path_lower
        or file_name.startswith("test_")
        or file_name.endswith("_test.py")
        or ".test." in file_name
        or ".spec." in file_name
    ):
        return "test"

    # Dependency manifests
    if file_name in _DEPENDENCY_FILES:
        return "dependency"

    # Build files
    if file_name in _BUILD_FILES or file_name.startswith("dockerfile"):
        return "build"

    # Documentation
    if (
        path_lower.startswith("docs/")
        or "/docs/" in path_lower
        or file_name.endswith((".md", ".rst", ".txt"))
    ):
        return "docs"

    # Configuration files
    if (
        path_lower.startswith("config/")
        or "/config/" in path_lower
        or file_name.endswith((".yaml", ".yml", ".json", ".toml", ".ini", ".cfg"))
        or file_name.startswith(".env")
    ):
        return "config"

    # Source code
    lang = detect_language(file_path)
    if lang in {
        "python",
        "javascript",
        "typescript",
        "go",
        "rust",
        "java",
        "c",
        "cpp",
        "ruby",
        "php",
        "sql",
    }:
        return "source"

    return "other"


def normalize_diff_hunk_headers(diff_text: str) -> str:
    """Normalize unified diff hunk line counts if slightly malformed."""
    import re

    lines = diff_text.splitlines(keepends=True)
    new_lines: list[str] = []
    i = 0
    hunk_re = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)$")
    while i < len(lines):
        line = lines[i]
        m = hunk_re.match(line)
        if m:
            s_start = int(m.group(1))
            t_start = int(m.group(2))
            rest = m.group(3)
            j = i + 1
            s_count = 0
            t_count = 0
            while j < len(lines):
                if lines[j].startswith(("--- ", "+++ ", "diff --git ", "@@ ")):
                    break
                hl = lines[j]
                if hl.startswith("+"):
                    t_count += 1
                elif hl.startswith("-"):
                    s_count += 1
                elif hl.startswith(" "):
                    s_count += 1
                    t_count += 1
                elif hl.startswith("\\"):
                    pass
                else:
                    s_count += 1
                    t_count += 1
                j += 1
            new_lines.append(f"@@ -{s_start},{s_count} +{t_start},{t_count} @@{rest}\n")
            new_lines.extend(lines[i + 1 : j])
            i = j
        else:
            new_lines.append(line)
            i += 1
    return "".join(new_lines)


def parse_diff_text(
    raw_diff: str, source: str = "diff", max_lines: int = 5000
) -> tuple[list[FileChange], str]:
    """Parse unified diff text into a list of FileChange models, truncating safely if excessive."""
    if not raw_diff or not raw_diff.strip():
        # Empty diff
        change_id = hashlib.sha256(b"empty").hexdigest()[:10]
        return [], change_id

    diff_lines = raw_diff.splitlines(keepends=True)
    if len(diff_lines) > max_lines:
        logger.warning(
            "Diff truncated: diff exceeds %d lines (total %d). Truncating safely.",
            max_lines,
            len(diff_lines),
        )
        cutoff = max_lines
        for idx in range(max_lines - 1, 0, -1):
            if diff_lines[idx].startswith("diff --git ") or diff_lines[idx].startswith("--- "):
                cutoff = idx
                break
        raw_diff = "".join(diff_lines[:cutoff])

    # Compute stable change ID from diff content
    change_id = hashlib.sha256(raw_diff.encode("utf-8")).hexdigest()[:10]

    try:
        patch_set = PatchSet(raw_diff)
    except UnidiffParseError:
        # Attempt recovery via hunk normalization
        try:
            normalized = normalize_diff_hunk_headers(raw_diff)
            patch_set = PatchSet(normalized)
        except UnidiffParseError as err:
            raise ValueError(f"Failed to parse unified diff: {err}") from err

    if not patch_set and raw_diff.strip():
        raise ValueError(
            "Failed to parse unified diff: no valid file diffs or hunks found in input."
        )

    file_changes: list[FileChange] = []

    for patched_file in patch_set:
        raw_path = patched_file.path
        # Sanitise path against path traversal
        clean_path = Path(raw_path).as_posix().lstrip("/").replace("../", "")
        if not clean_path:
            clean_path = "unnamed_file"
        path = clean_path
        is_binary = getattr(patched_file, "is_binary_file", False)

        change_type: Literal["added", "modified", "deleted", "renamed"]
        if patched_file.is_added_file:
            change_type = "added"
        elif patched_file.is_removed_file:
            change_type = "deleted"
        elif getattr(patched_file, "is_rename", False):
            change_type = "renamed"
        else:
            change_type = "modified"

        language = detect_language(path)
        role = detect_file_role(path)

        hunks: list[HunkInfo] = []
        if not is_binary:
            for hunk in patched_file:
                added_lines: list[LineInfo] = []
                removed_lines: list[LineInfo] = []
                context_lines: list[LineInfo] = []

                for line in hunk:
                    if line.is_added:
                        added_lines.append(
                            LineInfo(
                                line_number=line.target_line_no or 0,
                                content=line.value.rstrip("\r\n"),
                            )
                        )
                    elif line.is_removed:
                        removed_lines.append(
                            LineInfo(
                                line_number=line.source_line_no or 0,
                                content=line.value.rstrip("\r\n"),
                            )
                        )
                    elif line.is_context:
                        context_lines.append(
                            LineInfo(
                                line_number=line.target_line_no or line.source_line_no or 0,
                                content=line.value.rstrip("\r\n"),
                            )
                        )

                hunks.append(
                    HunkInfo(
                        source_start=hunk.source_start,
                        source_length=hunk.source_length,
                        target_start=hunk.target_start,
                        target_length=hunk.target_length,
                        added_lines=added_lines,
                        removed_lines=removed_lines,
                        context_lines=context_lines,
                        raw_hunk=str(hunk),
                    )
                )

        file_changes.append(
            FileChange(
                path=path,
                change_type=change_type,
                language=language,
                role=role,
                lines_added=patched_file.added,
                lines_removed=patched_file.removed,
                hunks=hunks,
                is_binary=is_binary,
            )
        )

    return file_changes, change_id


def load_diff_from_file(file_path: str | Path) -> ChangeState:
    """Load unified diff from a local file and return an initialized ChangeState."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Diff file not found: {file_path}")

    raw_diff = path.read_text(encoding="utf-8", errors="replace")
    files, change_id = parse_diff_text(raw_diff, source=str(path))
    return ChangeState(
        change_id=change_id,
        source=str(path),
        raw_diff=raw_diff,
        files=files,
    )


def load_diff_from_stdin(raw_diff: str) -> ChangeState:
    """Load unified diff from raw text (e.g. piped stdin)."""
    files, change_id = parse_diff_text(raw_diff, source="stdin")
    return ChangeState(
        change_id=change_id,
        source="stdin",
        raw_diff=raw_diff,
        files=files,
    )


def load_diff_from_git(commit_range: str, repo_path: str | Path = ".") -> ChangeState:
    """Load diff from a git commit range (e.g. 'HEAD~1..HEAD' or 'main..feature')."""
    cmd = ["git", "diff", commit_range]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            check=True,
        )
        raw_diff = proc.stdout
    except subprocess.CalledProcessError as err:
        raise RuntimeError(f"Git diff command failed: {err.stderr}") from err

    files, change_id = parse_diff_text(raw_diff, source=f"git:{commit_range}")
    return ChangeState(
        change_id=change_id,
        source=f"git:{commit_range}",
        raw_diff=raw_diff,
        files=files,
    )
