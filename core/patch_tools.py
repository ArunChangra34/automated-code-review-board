"""In-memory unified diff patch application, syntax checking, and verification loop."""

from __future__ import annotations

import ast
import json
from typing import Literal

import yaml
from unidiff import PatchSet

from core.diff_loader import (
    normalize_diff_hunk_headers,
    parse_diff_text,
)
from core.models import Finding, PatchVerification, Severity
from plugins.security_plugin import SecurityPlugin
from plugins.style_plugin import StylePlugin


def apply_unified_diff_in_memory(
    original_text: str,
    patch_text: str,
) -> tuple[bool, str, str]:
    """Apply a unified diff patch string to original text entirely in-memory."""
    if not patch_text or not patch_text.strip():
        return False, "", "Empty patch provided"

    try:
        normalized = normalize_diff_hunk_headers(patch_text)
        patch_set = PatchSet(normalized)
    except Exception as err:
        return False, "", f"Malformed unified diff patch: {err}"

    if not patch_set:
        return False, "", "No file changes found in patch"

    lines = original_text.splitlines(keepends=True)
    patched_file = patch_set[0]

    # Apply hunks in reverse line order so preceding line offsets remain unaffected
    for hunk in reversed(list(patched_file)):
        s_start = max(0, hunk.source_start - 1)
        source_expected: list[str] = []
        target_replacement: list[str] = []

        for line in hunk:
            if line.is_context:
                source_expected.append(line.value)
                target_replacement.append(line.value)
            elif line.is_removed:
                source_expected.append(line.value)
            elif line.is_added:
                target_replacement.append(line.value)

        s_len = len(source_expected)
        matched = False
        match_idx = -1

        # Search around expected line with sliding fuzzy window
        for offset in [0, 1, -1, 2, -2, 3, -3, 4, -4, 5, -5]:
            idx = s_start + offset
            if 0 <= idx and idx + s_len <= len(lines):
                window = lines[idx : idx + s_len]
                if [w.rstrip("\r\n") for w in window] == [
                    e.rstrip("\r\n") for e in source_expected
                ]:
                    matched = True
                    match_idx = idx
                    break

        if not matched:
            return False, "", f"Hunk at line {hunk.source_start} failed to apply: context mismatch"

        lines[match_idx : match_idx + s_len] = target_replacement

    return True, "".join(lines), ""


def check_syntax(content: str, language: str) -> tuple[bool, str]:
    """Validate syntax of modified file content."""
    if language == "python":
        try:
            ast.parse(content)
            return True, ""
        except SyntaxError as err:
            return False, f"Python SyntaxError: {err}"
    elif language == "json":
        try:
            json.loads(content)
            return True, ""
        except Exception as err:
            return False, f"JSON parse error: {err}"
    elif language == "yaml":
        try:
            yaml.safe_load(content)
            return True, ""
        except Exception as err:
            return False, f"YAML parse error: {err}"

    return True, ""


def verify_patch(
    finding: Finding,
    original_content: str,
    patch_text: str,
    language: str,
    file_path: str,
) -> PatchVerification:
    """Execute Patch Verification Loop (Fix-and-Re-Review)."""
    # Step 1: Clean in-memory application
    applies, patched_text, apply_err = apply_unified_diff_in_memory(original_content, patch_text)
    if not applies:
        return PatchVerification(
            applies_cleanly=False,
            syntax_ok=False,
            original_finding_resolved=False,
            new_findings_introduced=[],
            verdict="REJECTED",
            details=f"Patch application failed: {apply_err}",
        )

    # Step 2: Syntax Check
    syntax_ok, syntax_err = check_syntax(patched_text, language)
    if not syntax_ok:
        return PatchVerification(
            applies_cleanly=True,
            syntax_ok=False,
            original_finding_resolved=False,
            new_findings_introduced=[],
            verdict="REJECTED",
            details=f"Patched content failed syntax check: {syntax_err}",
        )

    # Step 3: Run baseline checkers on original vs patched content
    sec_plugin = SecurityPlugin()
    sty_plugin = StylePlugin()

    def _analyze_text(text: str) -> list[Finding]:
        virtual_diff = (
            f"--- a/{file_path}\n"
            f"+++ b/{file_path}\n"
            f"@@ -1,1 +1,{len(text.splitlines())} @@\n"
            + "\n".join("+" + line for line in text.splitlines())
            + "\n"
        )
        try:
            files, _ = parse_diff_text(virtual_diff)
        except Exception:
            files = []
        if not files:
            return []
        res: list[Finding] = []
        res.extend(sec_plugin.check_security(files))
        res.extend(sty_plugin.check_style(files))
        return res

    pre_findings = _analyze_text(original_content)
    post_findings = _analyze_text(patched_text)

    pre_rule_ids = {f.rule_id for f in pre_findings}
    post_rule_ids = {f.rule_id for f in post_findings}

    # Step 4: Check if original finding resolved
    original_resolved = finding.rule_id not in post_rule_ids

    # Step 5: Check for newly introduced findings
    new_findings = [f for f in post_findings if f.rule_id not in pre_rule_ids]
    new_severe = [f for f in new_findings if f.severity in (Severity.CRITICAL, Severity.HIGH)]

    if not original_resolved or new_severe:
        verdict: Literal["VERIFIED", "PARTIAL", "REJECTED"] = "REJECTED"
        details = (
            f"Verification rejected: original issue {finding.rule_id} still present in patched code"
            if not original_resolved
            else f"Verification rejected: introduced {len(new_severe)} severe new finding(s)"
        )
    elif new_findings:
        verdict = "PARTIAL"
        details = f"Verified cleanly; {len(new_findings)} minor advisory note(s) introduced"
    else:
        verdict = "VERIFIED"
        details = "Patch applies cleanly, syntax is valid, original issue resolved, and zero new findings introduced."

    return PatchVerification(
        applies_cleanly=True,
        syntax_ok=True,
        original_finding_resolved=original_resolved,
        new_findings_introduced=new_findings,
        verdict=verdict,
        details=details,
    )
