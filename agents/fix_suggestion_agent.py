"""Fix-Suggestion Agent proposing and machine-verifying concrete patches for findings."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from semantic_kernel import Kernel

from agents.base_agent import BaseAgent
from config.settings import Settings
from core.diff_loader import detect_language
from core.logging_setup import redact_secrets_in_text
from core.models import (
    Category,
    Finding,
    FixSuggestion,
    PatchVerification,
    Severity,
    SuggestedPatch,
)
from core.patch_tools import check_syntax, verify_patch
from core.retrieval import KnowledgeBase, get_knowledge_base
from core.state import ChangeState

# Maximum replacement block size accepted from an LLM response
_MAX_REPLACEMENT_LINES = 40


class FixSuggestionAgent(BaseAgent):
    """Proposes concrete unified-diff remediation patches and executes the Patch Verification Loop.

    In offline / 'always' mode: generates a deterministic rule-based template patch for the
    single highest-severity (rank-1) finding and verifies it.

    In LLM mode (llm_enabled=True): additionally generates per-finding suggestions for every
    eligible finding up to fix_max_findings, using one concurrent LLM call per finding.
    """

    def __init__(
        self,
        kernel: Kernel,
        settings: Settings | None = None,
        kb: KnowledgeBase | None = None,
    ):
        self.kb = kb or get_knowledge_base()
        instructions = (
            "You are the Fix-Suggestion Agent. Your purpose is to generate an exact, machine-verified "
            "unified-diff patch for findings identified in the review. "
            "Every proposed patch is strictly verified by re-reviewing the patched code."
        )
        # Create a dedicated kernel with no tool plugins to prevent tool-calling overhead
        clean_kernel = Kernel()
        for svc in kernel.services.values():
            clean_kernel.add_service(svc)

        super().__init__(
            name="fix_suggestion_agent",
            description="Proposes and verifies automated remediation patches for review findings",
            instructions=instructions,
            category=Category.DIFF,
            kernel=clean_kernel,
            settings=settings,
        )

    # ------------------------------------------------------------------
    # Content extraction helpers
    # ------------------------------------------------------------------

    def _extract_file_content_from_diff(self, file_path: str, state: ChangeState) -> str:
        """Reconstruct added file content from diff hunks for in-memory patch testing."""
        lines: list[str] = []
        for f in state.files:
            if f.path == file_path:
                for hunk in f.hunks:
                    # Prefer target representation
                    for line in hunk.added_lines:
                        lines.append(line.content)
                    if not hunk.added_lines:
                        for line in hunk.context_lines:
                            lines.append(line.content)
        return "\n".join(lines) + "\n"

    def _get_added_lines_window(
        self, file_path: str, state: ChangeState, center: int | None, window: int = 15
    ) -> list[tuple[int, str]]:
        """Return (line_number, content) pairs for added lines near *center* in a file."""
        pairs: list[tuple[int, str]] = []
        for fc in state.files:
            if fc.path == file_path:
                for hunk in fc.hunks:
                    for li in hunk.added_lines:
                        pairs.append((li.line_number, li.content))
        if center is None or not pairs:
            return pairs
        return [(ln, content) for ln, content in pairs if abs(ln - center) <= window]

    def _added_line_numbers(self, file_path: str, state: ChangeState) -> set[int]:
        """Return the set of all added line numbers for a given file path."""
        result: set[int] = set()
        for fc in state.files:
            if fc.path == file_path:
                for hunk in fc.hunks:
                    for li in hunk.added_lines:
                        result.add(li.line_number)
        return result

    # ------------------------------------------------------------------
    # Template (deterministic rule-based) patch generation
    # ------------------------------------------------------------------

    def generate_template_patch(
        self,
        finding: Finding,
        file_path: str,
        content: str,
    ) -> tuple[str, str, list[str], list[str]]:
        """Generate deterministic unified-diff patch based on known rule IDs.

        Returns: (unified_diff, explanation, new_imports, followups)
        """
        lines = content.splitlines(keepends=True)
        rule_id = finding.rule_id
        target_path = file_path or "file.py"

        # Template 1: SEC-SQLI-001 (SQL Injection Parameterization)
        if rule_id == "SEC-SQLI-001":
            for idx, line in enumerate(lines):
                # Match f-string query e.g. query = f"SELECT ... WHERE username = '{username}'"
                m = re.search(
                    r"""query\s*=\s*f['"]([^'"]*)\bWHERE\s+([a-zA-Z0-9_]+)\s*=\s*['"]?\{([a-zA-Z0-9_]+)\}['"]?['"]""",
                    line,
                )
                if m:
                    prefix = line[: line.find("query")]
                    base_sql = m.group(1)
                    col = m.group(2)
                    var_name = m.group(3)

                    # Look for cursor.execute on subsequent line
                    exec_idx = -1
                    for j in range(idx + 1, min(idx + 5, len(lines))):
                        if "cursor.execute(" in lines[j]:
                            exec_idx = j
                            break

                    old_block = lines[idx] + (lines[exec_idx] if exec_idx != -1 else "")
                    new_query = f'{prefix}query = "{base_sql}WHERE {col} = %s"\n'
                    new_exec = (
                        f"{prefix}cursor.execute(query, ({var_name},))\n" if exec_idx != -1 else ""
                    )
                    new_block = new_query + new_exec

                    patch_text = (
                        f"--- a/{target_path}\n"
                        f"+++ b/{target_path}\n"
                        f"@@ -{idx + 1},{2 if exec_idx != -1 else 1} +{idx + 1},{2 if exec_idx != -1 else 1} @@\n"
                        + "".join("-" + ln for ln in old_block.splitlines(keepends=True))
                        + "".join("+" + ln for ln in new_block.splitlines(keepends=True))
                    )
                    explanation = "Parameterize SQL query using %s placeholder and tuple argument to eliminate SQL injection."
                    return (
                        patch_text,
                        explanation,
                        [],
                        ["Verify database cursor driver supports standard %s parameter binding."],
                    )

        # Template 2: SEC-SECRET-001 / SEC-SECRET-002 (Hard-Coded Secret externalization)
        if rule_id in ("SEC-SECRET-001", "SEC-SECRET-002", "SEC-SECRET-004"):
            for idx, line in enumerate(lines):
                if re.search(
                    r"""(?:AKIA|ghp_|xox|sk_live_|token|password|key)\b""", line, re.IGNORECASE
                ):
                    m_assign = re.match(r"^(\s*)([A-Z0-9_]+)\s*=\s*['\"][^'\"]+['\"](.*)$", line)
                    if m_assign:
                        indent = m_assign.group(1)
                        var_name = m_assign.group(2)
                        suffix = m_assign.group(3)
                        env_var = "AWS_ACCESS_KEY_ID" if "AWS" in var_name else f"{var_name}_SECRET"

                        old_block = line
                        new_block = (
                            f'{indent}{var_name} = os.environ.get("{env_var}", ""){suffix}\n'
                        )

                        patch_text = (
                            f"--- a/{target_path}\n"
                            f"+++ b/{target_path}\n"
                            f"@@ -{idx + 1},1 +{idx + 1},1 @@\n"
                            f"-{old_block}"
                            f"+{new_block}"
                        )
                        explanation = "Externalize hard-coded credential to environment variable lookup via os.environ."
                        return (
                            patch_text,
                            explanation,
                            ["import os"],
                            [
                                "Immediately revoke and rotate the exposed secret.",
                                f"Set '{env_var}' in runtime environment.",
                            ],
                        )

        # Template 3: SEC-CMDI-001 (Command Injection shell=False)
        if rule_id == "SEC-CMDI-001":
            for idx, line in enumerate(lines):
                if "shell=True" in line:
                    old_block = line
                    new_block = line.replace("shell=True", "shell=False")
                    patch_text = (
                        f"--- a/{target_path}\n"
                        f"+++ b/{target_path}\n"
                        f"@@ -{idx + 1},1 +{idx + 1},1 @@\n"
                        f"-{old_block}"
                        f"+{new_block}"
                    )
                    explanation = (
                        "Disable shell interpolation by specifying shell=False with argument list."
                    )
                    return patch_text, explanation, [], []

        # Template 4: STY-EXCEPT-001 (Bare except)
        if rule_id == "STY-EXCEPT-001":
            for idx, line in enumerate(lines):
                if re.search(r"^\s*except\s*:", line):
                    old_block = line
                    new_block = line.replace("except:", "except Exception as err:")
                    patch_text = (
                        f"--- a/{target_path}\n"
                        f"+++ b/{target_path}\n"
                        f"@@ -{idx + 1},1 +{idx + 1},1 @@\n"
                        f"-{old_block}"
                        f"+{new_block}"
                    )
                    explanation = "Catch 'Exception' rather than bare 'except' to preserve system-exit signals."
                    return patch_text, explanation, [], []

        # Fallback if no automated template applies
        return (
            "",
            "Manual architectural remediation required. Automated patch could not be safely synthesized.",
            [],
            [],
        )

    # ------------------------------------------------------------------
    # LLM fix generation (one finding at a time)
    # ------------------------------------------------------------------

    async def _call_llm(self, prompt: str) -> str:
        """Invoke the Semantic Kernel agent and return the raw text response."""
        from semantic_kernel.connectors.ai.prompt_execution_settings import PromptExecutionSettings

        response_text = ""
        settings = PromptExecutionSettings(max_tokens=512)
        async for msg in self.sk_agent.invoke(messages=prompt, settings=settings):
            if msg.content:
                response_text += str(msg.content)
        return response_text

    def _build_fix_prompt(self, finding: Finding, state: ChangeState) -> str:
        """Build the per-finding LLM prompt for fix generation."""
        # Retrieve knowledge base grounding — cap at 300 chars to save tokens
        kb_recipe = ""
        try:
            chunk = self.kb.lookup_rule(finding.rule_id)
            if chunk:
                kb_recipe = chunk.content[:300]
            else:
                search_results = self.kb.search(f"{finding.title} {finding.description}", top_k=1)
                if search_results:
                    kb_recipe = search_results[0][0].content[:300]
        except Exception:
            pass

        # Collect the added-lines window around the finding
        window = self._get_added_lines_window(
            finding.file_path or "", state, finding.line_start, window=15
        )
        lines_text = "\n".join(f"  {ln}: {content}" for ln, content in window) if window else ""
        lines_text = redact_secrets_in_text(lines_text)

        # Redact any secrets from the snippet shown to the model
        snippet = redact_secrets_in_text(finding.code_snippet or "")

        prompt = (
            "Remediation engine. Return ONLY strict JSON, no markdown, no prose.\n"
            f"rule:{finding.rule_id} sev:{finding.severity.value} "
            f"file:{finding.file_path or 'unknown'} lines:{finding.line_start}-{finding.line_end}\n"
            f"title:{finding.title}\n"
            f"rec:{finding.recommendation}\n"
            f"snippet:{snippet}\n"
            f"added_lines:\n{lines_text}\n"
            f"recipe:{kb_recipe}\n"
            "Return one JSON shape:\n"
            '{"kind":"replace","file_path":"...","start_line":<int>,"end_line":<int>,'
            '"replacement_lines":["..."],"explanation":"...","new_imports":[],"followups":[]}\n'
            '{"kind":"new_file","file_path":"tests/test_x.py","content":"...","explanation":"..."}\n'
            '{"kind":"manual","explanation":"..."}\n'
            f"Rules: start_line..end_line must be ADDED lines in diff. "
            f"Max {_MAX_REPLACEMENT_LINES} replacement lines. No secrets. Use manual if unsafe.\n"
        )
        return redact_secrets_in_text(prompt)

    def _build_display_diff(
        self,
        file_path: str,
        start_line: int,
        end_line: int,
        old_lines: list[str],
        new_lines: list[str],
    ) -> str:
        """Build a display-only unified diff using real line numbers."""
        hunk_len_old = len(old_lines)
        hunk_len_new = len(new_lines)
        header = (
            f"--- a/{file_path}\n"
            f"+++ b/{file_path}\n"
            f"@@ -{start_line},{hunk_len_old} +{start_line},{hunk_len_new} @@\n"
        )
        removed = "".join(f"-{ln}\n" for ln in old_lines)
        added = "".join(f"+{ln}\n" for ln in new_lines)
        return header + removed + added

    async def _generate_llm_fix(self, finding: Finding, state: ChangeState) -> FixSuggestion:
        """Generate and verify a single LLM fix suggestion for one finding.

        Returns a FixSuggestion regardless of success; sets note and kind appropriately.
        """
        file_path = finding.file_path or ""
        language = detect_language(file_path)
        content = self._extract_file_content_from_diff(file_path, state)
        added_lnos = self._added_line_numbers(file_path, state)

        prompt = self._build_fix_prompt(finding, state)

        # Attempt raw LLM call; network/API errors bubble up so _bounded tracks call failure
        try:
            raw_response = await self._call_llm(prompt)
        except Exception as err:
            self.logger.warning("LLM invocation error for finding %s: %s", finding.id, err)
            raise err

        parsed: dict[str, Any] = {}

        # Parse JSON with one retry
        for attempt in range(2):
            cleaned = raw_response.strip()
            for fence in ("```json", "```"):
                if cleaned.startswith(fence):
                    cleaned = cleaned[len(fence) :]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            try:
                parsed = json.loads(cleaned.strip())
                break
            except Exception as parse_err:
                if attempt == 0:
                    retry_prompt = (
                        f"Previous output failed JSON parsing: {parse_err}. "
                        "Return ONLY valid JSON, no prose."
                    )
                    try:
                        raw_response = await self._call_llm(retry_prompt)
                        continue
                    except Exception as err:
                        raise err
                # Both attempts failed to parse JSON → manual guidance
                return FixSuggestion(
                    finding_id=finding.id,
                    rule_id=finding.rule_id,
                    severity=finding.severity,
                    file_path=file_path,
                    line_start=finding.line_start,
                    line_end=finding.line_end,
                    kind="manual",
                    source="llm",
                    explanation=f"Response could not be parsed as JSON: {parse_err}",
                    note="manual guidance",
                )

        kind = parsed.get("kind", "manual")

        # --- Handle "new_file" kind (e.g. a generated test module) ---
        if kind == "new_file":
            new_file_path = parsed.get("file_path", f"tests/test_{finding.rule_id.lower()}.py")
            new_content = parsed.get("content", "")
            explanation = parsed.get("explanation", "")
            syntax_ok, syntax_err = check_syntax(new_content, detect_language(new_file_path))
            # Build a diff against /dev/null
            display_diff = (
                f"--- /dev/null\n"
                f"+++ b/{new_file_path}\n"
                f"@@ -0,0 +1,{len(new_content.splitlines())} @@\n"
                + "".join(f"+{ln}\n" for ln in new_content.splitlines())
            )
            if not syntax_ok:
                return FixSuggestion(
                    finding_id=finding.id,
                    rule_id=finding.rule_id,
                    severity=finding.severity,
                    file_path=new_file_path,
                    line_start=None,
                    line_end=None,
                    kind="manual",
                    source="llm",
                    explanation=explanation,
                    note=f"rejected: new_file content failed syntax check: {syntax_err}",
                )
            return FixSuggestion(
                finding_id=finding.id,
                rule_id=finding.rule_id,
                severity=finding.severity,
                file_path=new_file_path,
                line_start=None,
                line_end=None,
                kind="new_file",
                source="llm",
                explanation=explanation,
                unified_diff=display_diff,
                note="new test file, syntax-checked only (not behaviour-verified)",
                verification=None,
            )

        # --- Handle "manual" kind ---
        if kind == "manual":
            return FixSuggestion(
                finding_id=finding.id,
                rule_id=finding.rule_id,
                severity=finding.severity,
                file_path=file_path,
                line_start=finding.line_start,
                line_end=finding.line_end,
                kind="manual",
                source="llm",
                explanation=parsed.get("explanation", "Manual remediation required."),
                note="manual guidance",
            )

        # --- Handle "replace" kind ---
        if kind != "replace":
            return FixSuggestion(
                finding_id=finding.id,
                rule_id=finding.rule_id,
                severity=finding.severity,
                file_path=file_path,
                line_start=finding.line_start,
                line_end=finding.line_end,
                kind="manual",
                source="llm",
                explanation=parsed.get("explanation", "Unrecognised fix kind returned."),
                note=f"manual guidance: unrecognised kind '{kind}'",
            )

        start_line: int = parsed.get("start_line", 0)
        end_line: int = parsed.get("end_line", start_line)
        replacement_lines: list[str] = parsed.get("replacement_lines", [])
        explanation_str: str = parsed.get("explanation", "")
        new_imports: list[str] = parsed.get("new_imports", [])
        followups: list[str] = parsed.get("followups", [])

        # Validation: lines must be in diff
        lines_in_range = set(range(start_line, end_line + 1))
        if not lines_in_range.issubset(added_lnos) or not lines_in_range:
            return FixSuggestion(
                finding_id=finding.id,
                rule_id=finding.rule_id,
                severity=finding.severity,
                file_path=file_path,
                line_start=finding.line_start,
                line_end=finding.line_end,
                kind="manual",
                source="llm",
                explanation=explanation_str,
                note="manual guidance: replacement lines not all in added-lines of this diff",
            )

        # Cap replacement size
        if len(replacement_lines) > _MAX_REPLACEMENT_LINES:
            replacement_lines = replacement_lines[:_MAX_REPLACEMENT_LINES]

        # Reconstruct old lines from content
        content_lines = content.splitlines()
        old_lines = content_lines[start_line - 1 : end_line] if content_lines else []

        display_diff = self._build_display_diff(
            file_path, start_line, end_line, old_lines, replacement_lines
        )

        # Build a verification diff relative to the reconstructed mini-file
        verify_diff = (
            f"--- a/{file_path}\n"
            f"+++ b/{file_path}\n"
            f"@@ -{start_line},{len(old_lines)} +{start_line},{len(replacement_lines)} @@\n"
            + "".join(f"-{ln}\n" for ln in old_lines)
            + "".join(f"+{ln}\n" for ln in replacement_lines)
        )

        verification = verify_patch(
            finding=finding,
            original_content=content,
            patch_text=verify_diff,
            language=language,
            file_path=file_path,
        )

        if verification.verdict == "REJECTED":
            return FixSuggestion(
                finding_id=finding.id,
                rule_id=finding.rule_id,
                severity=finding.severity,
                file_path=file_path,
                line_start=finding.line_start,
                line_end=finding.line_end,
                kind="manual",
                source="llm",
                explanation=explanation_str,
                new_imports=new_imports,
                followups=followups,
                note=f"rejected: {verification.details}",
                verification=verification,
            )

        return FixSuggestion(
            finding_id=finding.id,
            rule_id=finding.rule_id,
            severity=finding.severity,
            file_path=file_path,
            line_start=start_line,
            line_end=end_line,
            kind="replace",
            source="llm",
            explanation=explanation_str,
            unified_diff=display_diff,
            new_imports=new_imports,
            followups=followups,
            verification=verification,
            note="",
        )

    # ------------------------------------------------------------------
    # BaseAgent hooks
    # ------------------------------------------------------------------

    async def analyze_deterministic(self, state: ChangeState) -> list[Finding]:
        """Generate template patch for rank-1 finding (when fix_suggestions='always' or LLM mode).

        When fix_suggestions='never' or ('auto' and not llm_enabled): skip entirely.
        When fix_suggestions='always' (including offline): template patch for rank-1 only.
        When llm_enabled: template patch for rank-1 AND schedule LLM path in _augment_with_llm.
        """
        fix_policy = self.settings.fix_suggestions
        llm_on = self.settings.llm_enabled

        # Determine whether the template path runs
        run_template = fix_policy == "always" or (fix_policy == "auto" and llm_on)

        if not run_template:
            # offline + auto → produce nothing
            return []

        if not state.consolidated_review or not state.consolidated_review.priority_order:
            return []

        top_finding = state.consolidated_review.priority_order[0]
        file_path = top_finding.file_path or ""
        language = detect_language(file_path)

        content = self._extract_file_content_from_diff(file_path, state)
        if not content.strip() and top_finding.code_snippet:
            content = top_finding.code_snippet + "\n"

        patch_diff, explanation, new_imports, followups = self.generate_template_patch(
            top_finding, file_path, content
        )

        verification: PatchVerification | None = None
        if patch_diff:
            verification = verify_patch(
                finding=top_finding,
                original_content=content,
                patch_text=patch_diff,
                language=language,
                file_path=file_path,
            )

        suggested_patch = SuggestedPatch(
            finding_id=top_finding.id,
            file_path=file_path,
            unified_diff=patch_diff,
            explanation=explanation,
            new_imports=new_imports,
            followups=followups,
            verification=verification,
        )

        await state.set_suggested_patch(suggested_patch)
        return []

    async def _augment_with_llm(
        self, state: ChangeState, existing_findings: list[Finding]
    ) -> list[Finding]:
        """LLM path: generate per-finding fix suggestions for all eligible findings.

        Returns the findings list unchanged (this agent produces fix suggestions, not findings).
        """
        if not state.consolidated_review:
            return existing_findings

        # Select eligible findings (skip DIFF category and INFO severity)
        candidates = [
            f
            for f in state.consolidated_review.priority_order
            if f.category != Category.DIFF and f.severity != Severity.INFO
        ]
        candidates = candidates[: self.settings.fix_max_findings]

        if not candidates:
            return existing_findings

        semaphore = asyncio.Semaphore(self.settings.fix_llm_concurrency)

        async def _bounded(finding: Finding) -> FixSuggestion | None:
            async with semaphore:
                try:
                    return await self._generate_llm_fix(finding, state)
                except Exception as err:
                    self.logger.warning(
                        "LLM fix generation failed for finding %s: %s", finding.id, err
                    )
                    return None

        results = await asyncio.gather(*(_bounded(f) for f in candidates))
        suggestions: list[FixSuggestion] = [r for r in results if r is not None]

        if len(suggestions) == 0 and len(candidates) > 0:
            # All calls failed
            raise RuntimeError(
                f"All {len(candidates)} LLM fix calls failed; agent degraded gracefully."
            )

        # Sort by priority_rank of the parent finding
        rank_map = {f.id: (f.priority_rank or 9999) for f in candidates}
        suggestions.sort(key=lambda s: rank_map.get(s.finding_id, 9999))

        # Promote top verified LLM suggestion to suggested_patch if no template patch was set
        if not state.suggested_patch and suggestions:
            top = suggestions[0]
            if (
                top.kind in ("replace",)
                and top.unified_diff
                and (top.verification is None or top.verification.verdict != "REJECTED")
            ):
                promoted = SuggestedPatch(
                    finding_id=top.finding_id,
                    file_path=top.file_path,
                    unified_diff=top.unified_diff,
                    explanation=top.explanation,
                    new_imports=top.new_imports,
                    followups=top.followups,
                    verification=top.verification,
                )
                await state.set_suggested_patch(promoted)

        await state.set_fix_suggestions(suggestions)
        return existing_findings
