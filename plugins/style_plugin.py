"""Deterministic style and readability analysis plugin operating exclusively on added lines."""

from __future__ import annotations

import ast
import re
from typing import Annotated, Any

from semantic_kernel.functions import kernel_function

from config.settings import Settings, get_settings
from core.models import Category, FileChange, Finding, Severity
from core.retrieval import KnowledgeBase, get_knowledge_base

_PASCAL_CASE_RE = re.compile(r"^[A-Z][a-zA-Z0-9]*$")
_SNAKE_CASE_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
_CAMEL_CASE_RE = re.compile(r"^[a-z][a-zA-Z0-9]*$")

_COMMENTED_CODE_RE = re.compile(
    r"^\s*#\s*(def\s+|class\s+|if\s+|for\s+|while\s+|return\s+|import\s+|[a-zA-Z_]\w*\s*=)"
)
_TODO_RE = re.compile(r"(?i)\b(TODO|FIXME)\b(?!\s*\(|\s*\[|\s*:[A-Z]+-\d+)")
_DEBUG_PRINT_RE = re.compile(r"^\s*print\s*\(")
_DEBUG_CONSOLE_RE = re.compile(r"^\s*console\.(log|debug|warn|error)\s*\(")
_WILDCARD_IMPORT_RE = re.compile(r"^\s*from\s+[\w.]+\s+import\s+\*")
_BARE_EXCEPT_RE = re.compile(r"^\s*except\s*:")
_MUTABLE_DEFAULT_RE = re.compile(r"def\s+\w+\s*\([^)]*=\s*(\[\]|\{\}|set\(\))")


class CyclomaticComplexityVisitor(ast.NodeVisitor):
    """AST visitor to compute McCabe cyclomatic complexity."""

    def __init__(self) -> None:
        self.complexity = 1

    def visit_If(self, node: ast.If) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self.complexity += len(node.values) - 1
        self.generic_visit(node)


class StylePlugin:
    """Plugin enforcing style guidelines, naming standards, and readability limits."""

    def __init__(
        self,
        settings: Settings | None = None,
        kb: KnowledgeBase | None = None,
    ):
        self.settings = settings or get_settings()
        self.kb = kb or get_knowledge_base()

    def _get_citation(self, rule_id: str) -> str | None:
        """Resolve evidence source citation from knowledge base."""
        chunk = self.kb.lookup_rule(rule_id)
        if chunk:
            return chunk.citation
        results = self.kb.search(rule_id, top_k=1, category_filter="style")
        if results:
            return results[0][0].citation
        return None

    @kernel_function(
        name="check_style",
        description="Inspect added lines across file changes for style and readability violations",
    )
    def check_style(
        self,
        files: Annotated[list[FileChange], "List of parsed FileChange objects"],
    ) -> list[Finding]:
        """Perform comprehensive deterministic style check on added lines only."""
        findings: list[Finding] = []
        max_line_len = self.settings.max_line_length

        for f in files:
            if f.is_binary or f.role == "docs":
                continue

            for hunk in f.hunks:
                # 1. Line-by-line checks
                for line in hunk.added_lines:
                    text = line.content
                    line_no = line.line_number

                    # Rule STY-LEN-001: Maximum line length
                    if len(text) > max_line_len:
                        citation = self._get_citation("STY-LEN-001")
                        findings.append(
                            Finding(
                                id=Finding.generate_id(
                                    Category.STYLE, "STY-LEN-001", f.path, line_no
                                ),
                                category=Category.STYLE,
                                severity=Severity.LOW,
                                title=f"Line Length Exceeds Limit ({len(text)} > {max_line_len})",
                                description=f"Line {line_no} in '{f.path}' is {len(text)} characters long, exceeding the configured threshold of {max_line_len}.",
                                file_path=f.path,
                                line_start=line_no,
                                line_end=line_no,
                                code_snippet=text[:80] + "...",
                                rule_id="STY-LEN-001",
                                evidence_source=citation,
                                recommendation="Wrap long expressions using parentheses or extract intermediate helper variables.",
                                confidence=1.0 if citation else 0.85,
                                reported_by=["style_agent"],
                            )
                        )

                    # Rule STY-DEBUG-001 / STY-DEBUG-002: Leftover debug prints
                    if f.language == "python" and _DEBUG_PRINT_RE.search(text):
                        citation = self._get_citation("STY-DEBUG-001")
                        findings.append(
                            Finding(
                                id=Finding.generate_id(
                                    Category.STYLE, "STY-DEBUG-001", f.path, line_no
                                ),
                                category=Category.STYLE,
                                severity=Severity.LOW,
                                title="Leftover Debug Print Statement",
                                description=f"Found raw print() statement on line {line_no} in '{f.path}'.",
                                file_path=f.path,
                                line_start=line_no,
                                line_end=line_no,
                                code_snippet=text,
                                rule_id="STY-DEBUG-001",
                                evidence_source=citation,
                                recommendation="Replace print() with structured logger calls (e.g. logger.debug or logger.info).",
                                confidence=1.0 if citation else 0.85,
                                reported_by=["style_agent"],
                            )
                        )
                    elif f.language in ("javascript", "typescript") and _DEBUG_CONSOLE_RE.search(
                        text
                    ):
                        citation = self._get_citation("STY-DEBUG-002")
                        findings.append(
                            Finding(
                                id=Finding.generate_id(
                                    Category.STYLE, "STY-DEBUG-002", f.path, line_no
                                ),
                                category=Category.STYLE,
                                severity=Severity.LOW,
                                title="Leftover Console Debugging Statement",
                                description=f"Found console logging statement on line {line_no} in '{f.path}'.",
                                file_path=f.path,
                                line_start=line_no,
                                line_end=line_no,
                                code_snippet=text,
                                rule_id="STY-DEBUG-002",
                                evidence_source=citation,
                                recommendation="Remove debugging console statements before committing to production.",
                                confidence=1.0 if citation else 0.85,
                                reported_by=["style_agent"],
                            )
                        )

                    # Rule STY-DEAD-001: Commented-out dead code
                    if _COMMENTED_CODE_RE.search(text):
                        citation = self._get_citation("STY-DEAD-001")
                        findings.append(
                            Finding(
                                id=Finding.generate_id(
                                    Category.STYLE, "STY-DEAD-001", f.path, line_no
                                ),
                                category=Category.STYLE,
                                severity=Severity.LOW,
                                title="Commented-Out Dead Code",
                                description=f"Line {line_no} in '{f.path}' appears to contain commented-out source code.",
                                file_path=f.path,
                                line_start=line_no,
                                line_end=line_no,
                                code_snippet=text,
                                rule_id="STY-DEAD-001",
                                evidence_source=citation,
                                recommendation="Remove obsolete code. Git history preserves historical implementations.",
                                confidence=1.0 if citation else 0.85,
                                reported_by=["style_agent"],
                            )
                        )

                    # Rule STY-EXCEPT-001: Bare except clause
                    if f.language == "python" and _BARE_EXCEPT_RE.search(text):
                        citation = self._get_citation("STY-EXCEPT-001")
                        findings.append(
                            Finding(
                                id=Finding.generate_id(
                                    Category.STYLE, "STY-EXCEPT-001", f.path, line_no
                                ),
                                category=Category.STYLE,
                                severity=Severity.MEDIUM,
                                title="Bare Except Clause Catches SystemExit",
                                description=f"Bare 'except:' on line {line_no} in '{f.path}' catches all exceptions including system signals.",
                                file_path=f.path,
                                line_start=line_no,
                                line_end=line_no,
                                code_snippet=text,
                                rule_id="STY-EXCEPT-001",
                                evidence_source=citation,
                                recommendation="Catch explicit exception classes or 'except Exception:' to preserve system interrupts.",
                                confidence=1.0 if citation else 0.85,
                                reported_by=["style_agent"],
                            )
                        )

                    # Rule STY-IMPORT-001: Wildcard import
                    if f.language == "python" and _WILDCARD_IMPORT_RE.search(text):
                        citation = self._get_citation("STY-IMPORT-001")
                        findings.append(
                            Finding(
                                id=Finding.generate_id(
                                    Category.STYLE, "STY-IMPORT-001", f.path, line_no
                                ),
                                category=Category.STYLE,
                                severity=Severity.LOW,
                                title="Wildcard Import Pollutes Namespace",
                                description=f"Wildcard import on line {line_no} in '{f.path}'.",
                                file_path=f.path,
                                line_start=line_no,
                                line_end=line_no,
                                code_snippet=text,
                                rule_id="STY-IMPORT-001",
                                evidence_source=citation,
                                recommendation="Import specific required symbols explicitly.",
                                confidence=1.0 if citation else 0.85,
                                reported_by=["style_agent"],
                            )
                        )

                    # Rule STY-MUTABLE-001: Mutable default argument
                    if f.language == "python" and _MUTABLE_DEFAULT_RE.search(text):
                        citation = self._get_citation("STY-MUTABLE-001")
                        findings.append(
                            Finding(
                                id=Finding.generate_id(
                                    Category.STYLE, "STY-MUTABLE-001", f.path, line_no
                                ),
                                category=Category.STYLE,
                                severity=Severity.LOW,
                                title="Mutable Default Argument in Function Signature",
                                description=f"Function signature on line {line_no} in '{f.path}' uses a mutable default container.",
                                file_path=f.path,
                                line_start=line_no,
                                line_end=line_no,
                                code_snippet=text,
                                rule_id="STY-MUTABLE-001",
                                evidence_source=citation,
                                recommendation="Use 'None' as default value and initialize inside the function body.",
                                confidence=1.0 if citation else 0.85,
                                reported_by=["style_agent"],
                            )
                        )

                    # Rule STY-TODO-001: Unassigned TODO
                    if _TODO_RE.search(text):
                        citation = self._get_citation("STY-TODO-001")
                        findings.append(
                            Finding(
                                id=Finding.generate_id(
                                    Category.STYLE, "STY-TODO-001", f.path, line_no
                                ),
                                category=Category.STYLE,
                                severity=Severity.INFO,
                                title="Unannotated TODO / FIXME Marker",
                                description=f"Line {line_no} in '{f.path}' has an unassigned TODO/FIXME comment without issue reference.",
                                file_path=f.path,
                                line_start=line_no,
                                line_end=line_no,
                                code_snippet=text,
                                rule_id="STY-TODO-001",
                                evidence_source=citation,
                                recommendation="Add ticket reference e.g. 'TODO(PROJ-1234): description'.",
                                confidence=1.0 if citation else 0.85,
                                reported_by=["style_agent"],
                            )
                        )

                # 2. Python AST block checks (Naming, Docstrings, Complexity)
                if f.language == "python":
                    py_findings = self._check_python_ast(hunk.added_lines, f.path)
                    findings.extend(py_findings)

                # 3. JavaScript Naming checks
                if f.language in ("javascript", "typescript"):
                    js_findings = self._check_javascript_naming(hunk.added_lines, f.path)
                    findings.extend(js_findings)

        return findings

    def _check_python_ast(self, added_lines: list[Any], file_path: str) -> list[Finding]:
        """Perform AST-based structural checks on added Python lines."""
        findings: list[Finding] = []
        if not added_lines:
            return findings

        added_code = "\n".join(line_info.content for line_info in added_lines)
        line_offset = added_lines[0].line_number

        try:
            tree = ast.parse(added_code)
        except SyntaxError:
            # Code fragment may be incomplete; regex checks already executed
            return findings

        for node in ast.walk(tree):
            # Function definitions
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                rel_line = getattr(node, "lineno", 1)
                actual_line = line_offset + rel_line - 1

                # Rule STY-NAME-001: Function snake_case
                if not _SNAKE_CASE_RE.match(node.name) and not (
                    node.name.startswith("__") and node.name.endswith("__")
                ):
                    citation = self._get_citation("STY-NAME-001")
                    findings.append(
                        Finding(
                            id=Finding.generate_id(
                                Category.STYLE, "STY-NAME-001", file_path, actual_line
                            ),
                            category=Category.STYLE,
                            severity=Severity.LOW,
                            title=f"Non-Idiomatic Function Name '{node.name}'",
                            description=f"Function '{node.name}' on line {actual_line} does not follow snake_case naming conventions.",
                            file_path=file_path,
                            line_start=actual_line,
                            line_end=actual_line,
                            code_snippet=f"def {node.name}(...)",
                            rule_id="STY-NAME-001",
                            evidence_source=citation,
                            recommendation="Rename function to follow lowercase snake_case conventions.",
                            confidence=1.0 if citation else 0.85,
                            reported_by=["style_agent"],
                        )
                    )

                # Rule STY-DOC-001: Missing docstrings on public function
                if not node.name.startswith("_") and not ast.get_docstring(node):
                    citation = self._get_citation("STY-DOC-001")
                    findings.append(
                        Finding(
                            id=Finding.generate_id(
                                Category.STYLE, "STY-DOC-001", file_path, actual_line
                            ),
                            category=Category.STYLE,
                            severity=Severity.LOW,
                            title=f"Missing Docstring on Public Function '{node.name}'",
                            description=f"Public function '{node.name}' on line {actual_line} lacks a docstring description.",
                            file_path=file_path,
                            line_start=actual_line,
                            line_end=actual_line,
                            code_snippet=f"def {node.name}(...)",
                            rule_id="STY-DOC-001",
                            evidence_source=citation,
                            recommendation="Add a docstring explaining parameters, return values, and exceptions raised.",
                            confidence=1.0 if citation else 0.85,
                            reported_by=["style_agent"],
                        )
                    )

                # Rule STY-COMPLEX-001: Cyclomatic complexity
                visitor = CyclomaticComplexityVisitor()
                visitor.visit(node)
                max_complexity = self.settings.max_cyclomatic_complexity
                if visitor.complexity > max_complexity:
                    citation = self._get_citation("STY-COMPLEX-001")
                    findings.append(
                        Finding(
                            id=Finding.generate_id(
                                Category.STYLE, "STY-COMPLEX-001", file_path, actual_line
                            ),
                            category=Category.STYLE,
                            severity=Severity.MEDIUM,
                            title=f"High Cyclomatic Complexity in '{node.name}' ({visitor.complexity} > {max_complexity})",
                            description=f"Function '{node.name}' has a cyclomatic complexity of {visitor.complexity}, exceeding the maximum allowed ({max_complexity}).",
                            file_path=file_path,
                            line_start=actual_line,
                            line_end=actual_line,
                            code_snippet=f"def {node.name}(...)",
                            rule_id="STY-COMPLEX-001",
                            evidence_source=citation,
                            recommendation="Refactor branching and loop logic into smaller, single-purpose helper functions.",
                            confidence=1.0 if citation else 0.85,
                            reported_by=["style_agent"],
                        )
                    )

            # Class definitions
            elif isinstance(node, ast.ClassDef):
                rel_line = getattr(node, "lineno", 1)
                actual_line = line_offset + rel_line - 1

                # Rule STY-NAME-002: Class PascalCase
                if not _PASCAL_CASE_RE.match(node.name):
                    citation = self._get_citation("STY-NAME-002")
                    findings.append(
                        Finding(
                            id=Finding.generate_id(
                                Category.STYLE, "STY-NAME-002", file_path, actual_line
                            ),
                            category=Category.STYLE,
                            severity=Severity.LOW,
                            title=f"Non-Idiomatic Class Name '{node.name}'",
                            description=f"Class '{node.name}' on line {actual_line} does not follow PascalCase conventions.",
                            file_path=file_path,
                            line_start=actual_line,
                            line_end=actual_line,
                            code_snippet=f"class {node.name}:",
                            rule_id="STY-NAME-002",
                            evidence_source=citation,
                            recommendation="Rename class using PascalCase (UpperCamelCase).",
                            confidence=1.0 if citation else 0.85,
                            reported_by=["style_agent"],
                        )
                    )

        return findings

    def _check_javascript_naming(self, added_lines: list[Any], file_path: str) -> list[Finding]:
        """Check JavaScript / TypeScript function names for camelCase conventions."""
        findings: list[Finding] = []
        js_func_re = re.compile(r"function\s+([a-zA-Z0-9_]+)\s*\(")

        for line in added_lines:
            match = js_func_re.search(line.content)
            if match:
                func_name = match.group(1)
                if not _CAMEL_CASE_RE.match(func_name) and not _PASCAL_CASE_RE.match(func_name):
                    # Flag function that starts with uppercase or has snake_case
                    citation = self._get_citation("STY-NAME-004")
                    findings.append(
                        Finding(
                            id=Finding.generate_id(
                                Category.STYLE, "STY-NAME-004", file_path, line.line_number
                            ),
                            category=Category.STYLE,
                            severity=Severity.LOW,
                            title=f"Non-Idiomatic JavaScript Function Name '{func_name}'",
                            description=f"JavaScript function '{func_name}' on line {line.line_number} should use camelCase.",
                            file_path=file_path,
                            line_start=line.line_number,
                            line_end=line.line_number,
                            code_snippet=line.content,
                            rule_id="STY-NAME-004",
                            evidence_source=citation,
                            recommendation="Rename JavaScript functions to follow standard camelCase naming conventions.",
                            confidence=1.0 if citation else 0.85,
                            reported_by=["style_agent"],
                        )
                    )

        return findings
