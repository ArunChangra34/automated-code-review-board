"""Fix-Suggestion Agent proposing and machine-verifying concrete patches for the top finding."""

from __future__ import annotations

import re

from semantic_kernel import Kernel

from agents.base_agent import BaseAgent
from config.settings import Settings
from core.diff_loader import detect_language
from core.models import Category, Finding, PatchVerification, SuggestedPatch
from core.patch_tools import verify_patch
from core.retrieval import KnowledgeBase, get_knowledge_base
from core.state import ChangeState


class FixSuggestionAgent(BaseAgent):
    """Proposes concrete unified-diff remediation patches and executes the Patch Verification Loop."""

    def __init__(
        self,
        kernel: Kernel,
        settings: Settings | None = None,
        kb: KnowledgeBase | None = None,
    ):
        self.kb = kb or get_knowledge_base()
        instructions = (
            "You are the Fix-Suggestion Agent. Your purpose is to generate an exact, machine-verified "
            "unified-diff patch for the single highest-severity finding identified in the review. "
            "Every proposed patch is strictly verified by re-reviewing the patched code."
        )
        super().__init__(
            name="fix_suggestion_agent",
            description="Proposes and verifies automated remediation patch for the rank-1 finding",
            instructions=instructions,
            category=Category.DIFF,
            kernel=kernel,
            settings=settings,
        )

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
                    r"""query\s*=\s*f['"]([^'"]*)\bWHERE\s+([a-zA-Z0-9_]+)\s*=\s*['"]\{([a-zA-Z0-9_]+)\}['"]['"]""",
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

    async def analyze_deterministic(self, state: ChangeState) -> list[Finding]:
        """Propose patch for rank 1 finding, run verification loop, and record in state."""
        if not state.consolidated_review or not state.consolidated_review.priority_order:
            return []

        top_finding = state.consolidated_review.priority_order[0]
        file_path = top_finding.file_path or ""
        language = detect_language(file_path)

        # Retrieve reconstructed content
        content = self._extract_file_content_from_diff(file_path, state)
        if not content.strip() and top_finding.code_snippet:
            content = top_finding.code_snippet + "\n"

        # Generate patch
        patch_diff, explanation, new_imports, followups = self.generate_template_patch(
            top_finding, file_path, content
        )

        verification: PatchVerification | None = None
        if patch_diff:
            # Run Patch Verification Loop ("Fix-and-Re-Review")
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
