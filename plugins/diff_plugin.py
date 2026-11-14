"""Deterministic diff analysis plugin for file stats, symbol extraction, and risk area detection."""

from __future__ import annotations

import ast
import json
import re
from typing import Annotated

from semantic_kernel.functions import kernel_function

from core.models import ChangeSummary, FileChange

# Risk area detection patterns matching paths and added code lines
_RISK_KEYWORDS = {
    "auth": re.compile(r"(?i)\b(auth|login|password|token|credential|jwt|session|permission)\b"),
    "crypto": re.compile(r"(?i)\b(crypto|cipher|hash|md5|sha1|sha256|encrypt|decrypt|hmac)\b"),
    "payments": re.compile(r"(?i)\b(payment|billing|invoice|stripe|checkout|discount|pricing)\b"),
    "database": re.compile(
        r"(?i)\b(db|sql|repository|query|database|cursor|migration|select|insert|update|delete)\b"
    ),
    "file_io": re.compile(r"(?i)\b(open\s*\(|read_text|write_text|os\.path|shutil|tempfile)\b"),
    "network": re.compile(r"(?i)\b(socket|http|requests\.|urllib|connect|endpoint|url)\b"),
    "subprocess": re.compile(r"(?i)\b(subprocess|os\.system|popen|execv|shell\s*=\s*True)\b"),
}


class DiffPlugin:
    """Plugin providing deterministic diff parsing, symbol extraction, and risk metrics."""

    @kernel_function(
        name="classify_size",
        description="Classify change size into XS, S, M, L, or XL based on line change thresholds",
    )
    def classify_size(
        self,
        total_lines: Annotated[int, "Total lines added and removed"],
        size_thresholds_json: Annotated[str, "JSON string of size thresholds"] = "{}",
    ) -> str:
        """Classify change size based on total modified lines."""
        try:
            thresholds = json.loads(size_thresholds_json)
        except Exception:
            thresholds = {}

        xs = thresholds.get("XS", 20)
        s = thresholds.get("S", 100)
        m = thresholds.get("M", 300)
        l_thresh = thresholds.get("L", 800)

        if total_lines <= xs:
            return "XS"
        if total_lines <= s:
            return "S"
        if total_lines <= m:
            return "M"
        if total_lines <= l_thresh:
            return "L"
        return "XL"

    @kernel_function(
        name="detect_risk_areas",
        description="Detect sensitive domains touched by the changeset (auth, crypto, payments, etc.)",
    )
    def detect_risk_areas(
        self,
        files_json: Annotated[str, "JSON representation of list of FileChange models"],
    ) -> str:
        """Analyze file paths and added line contents for risk keywords."""
        try:
            files_data = json.loads(files_json)
        except Exception:
            return json.dumps([])

        detected: set[str] = set()
        for f in files_data:
            path = f.get("path", "")
            # Check path
            for domain, pattern in _RISK_KEYWORDS.items():
                if pattern.search(path):
                    detected.add(domain)

            # Check added line contents
            hunks = f.get("hunks", [])
            for hunk in hunks:
                added = hunk.get("added_lines", [])
                for line in added:
                    content = line.get("content", "")
                    for domain, pattern in _RISK_KEYWORDS.items():
                        if pattern.search(content):
                            detected.add(domain)

        return json.dumps(sorted(detected))

    def extract_symbols(self, files: list[FileChange]) -> list[str]:
        """Extract newly declared function and class names from added code."""
        symbols: list[str] = []
        py_def_re = re.compile(r"^\s*(?:async\s+)?def\s+([a-zA-Z0-9_]+)\s*\(")
        py_class_re = re.compile(r"^\s*class\s+([a-zA-Z0-9_]+)\s*[:\(]")
        js_func_re = re.compile(
            r"(?:function\s+([a-zA-Z0-9_]+)|(?:const|let|var)\s+([a-zA-Z0-9_]+)\s*=\s*(?:async\s*)?\()"
        )

        for f in files:
            for hunk in f.hunks:
                added_text = "\n".join(line_info.content for line_info in hunk.added_lines)

                # Python AST parsing attempt
                if f.language == "python":
                    try:
                        tree = ast.parse(added_text)
                        for node in ast.walk(tree):
                            if isinstance(
                                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                            ):
                                symbols.append(node.name)
                    except SyntaxError:
                        # Fallback to regex
                        for line in hunk.added_lines:
                            m_def = py_def_re.match(line.content)
                            if m_def:
                                symbols.append(m_def.group(1))
                            m_cls = py_class_re.match(line.content)
                            if m_cls:
                                symbols.append(m_cls.group(1))
                elif f.language in ("javascript", "typescript"):
                    for line in hunk.added_lines:
                        m_js = js_func_re.search(line.content)
                        if m_js:
                            sym = m_js.group(1) or m_js.group(2)
                            if sym:
                                symbols.append(sym)

        return sorted(list(set(symbols)))

    def summarize_change(
        self,
        files: list[FileChange],
        size_thresholds: dict[str, int] | None = None,
    ) -> ChangeSummary:
        """Construct full ChangeSummary model deterministically."""
        total_files = len(files)
        total_added = sum(f.lines_added for f in files)
        total_removed = sum(f.lines_removed for f in files)
        languages = sorted(list({f.language for f in files if f.language != "text"}))

        files_json = json.dumps([f.model_dump() for f in files])
        risk_areas = json.loads(self.detect_risk_areas(files_json))
        symbols = self.extract_symbols(files)

        size_class = self.classify_size(
            total_added + total_removed,
            json.dumps(size_thresholds or {}),
        )

        roles = sorted(list({f.role for f in files}))
        roles_desc = ", ".join(roles) if roles else "source"
        sym_desc = (
            f"introducing or modifying symbols: {', '.join(symbols)}"
            if symbols
            else "with no new top-level declarations"
        )
        risk_desc = (
            f"Sensitive areas touched: {', '.join(risk_areas)}."
            if risk_areas
            else "No sensitive risk areas flagged."
        )

        intent_summary = (
            f"This change touches {total_files} file(s) across {', '.join(languages) or 'various'} components "
            f"({roles_desc}) with +{total_added}/-{total_removed} lines changed (size: {size_class}), "
            f"{sym_desc}. {risk_desc}"
        )

        return ChangeSummary(
            title=f"Pull Request Review: {total_files} file(s) ({size_class})",
            intent_summary=intent_summary,
            files=files,
            total_files=total_files,
            lines_added=total_added,
            lines_removed=total_removed,
            languages=languages,
            size_class=size_class,  # type: ignore[arg-type]
            risk_areas=risk_areas,
            detected_symbols=symbols,
        )
