"""Test coverage analysis plugin calculating change test ratios and symbol coverage maps."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Annotated, Any

from semantic_kernel.functions import kernel_function

from core.models import Category, FileChange, Finding, Severity
from core.retrieval import KnowledgeBase, get_knowledge_base

_ASSERT_PATTERNS = re.compile(r"(?i)\b(assert\s+|self\.assert|pytest\.raises|expect\(|should\.)")
_ERROR_PATH_PATTERNS = re.compile(
    r"(?i)\b(pytest\.raises|assertRaises|toThrow|catch\s*\(|ValueError|TypeError|Exception)\b"
)


class CoveragePlugin:
    """Plugin evaluating test presence, symbol test coverage, and test quality metrics."""

    def __init__(self, kb: KnowledgeBase | None = None):
        self.kb = kb or get_knowledge_base()

    def _get_citation(self, rule_id: str) -> str | None:
        """Resolve evidence source citation from testing knowledge base."""
        chunk = self.kb.lookup_rule(rule_id)
        if chunk:
            return chunk.citation
        results = self.kb.search(rule_id, top_k=1, category_filter="testing")
        if results:
            return results[0][0].citation
        return None

    def extract_source_symbols(self, source_files: list[FileChange]) -> list[tuple[str, str, int]]:
        """Extract public function and class declarations (symbol_name, file_path, line_no)."""
        symbols: list[tuple[str, str, int]] = []
        py_func_re = re.compile(r"^\s*(?:async\s+)?def\s+([a-zA-Z0-9_]+)\s*\(")
        py_class_re = re.compile(r"^\s*class\s+([a-zA-Z0-9_]+)\s*[:\(]")
        js_func_re = re.compile(
            r"(?:function\s+([a-zA-Z0-9_]+)|(?:const|let)\s+([a-zA-Z0-9_]+)\s*=\s*(?:async\s*)?\()"
        )

        for f in source_files:
            for hunk in f.hunks:
                for line in hunk.added_lines:
                    text = line.content
                    line_no = line.line_number

                    if f.language == "python":
                        m_f = py_func_re.match(text)
                        if m_f:
                            name = m_f.group(1)
                            if not name.startswith("_"):
                                symbols.append((name, f.path, line_no))
                        m_c = py_class_re.match(text)
                        if m_c:
                            name = m_c.group(1)
                            if not name.startswith("_"):
                                symbols.append((name, f.path, line_no))
                    elif f.language in ("javascript", "typescript"):
                        m_js = js_func_re.search(text)
                        if m_js:
                            name = m_js.group(1) or m_js.group(2)
                            if name and not name.startswith("_"):
                                symbols.append((name, f.path, line_no))

        return symbols

    def parse_coverage_report(self, report_path: str | Path) -> dict[str, float]:
        """Parse Cobertura XML or JSON coverage report for line coverage percentages."""
        path = Path(report_path)
        if not path.exists():
            return {}

        results: dict[str, float] = {}
        try:
            if path.suffix.lower() == ".xml":
                tree = ET.parse(path)
                root = tree.getroot()
                for cls_elem in root.iter("class"):
                    filename = cls_elem.get("filename", "")
                    rate = float(cls_elem.get("line-rate", 0.0)) * 100.0
                    results[filename] = round(rate, 2)
            elif path.suffix.lower() == ".json":
                data = json.loads(path.read_text(encoding="utf-8"))
                files_dict = data.get("files", {})
                for fn, details in files_dict.items():
                    summary = details.get("summary", {})
                    pct = float(summary.get("percent_covered", 0.0))
                    results[fn] = round(pct, 2)
        except Exception:
            return {}

        return results

    @kernel_function(
        name="analyze_coverage",
        description="Compute change test ratio, per-symbol coverage map, and test quality signals",
    )
    def analyze_coverage(
        self,
        files: Annotated[list[FileChange], "List of parsed FileChange objects"],
        coverage_report_path: Annotated[str, "Optional path to coverage.xml or coverage.json"] = "",
    ) -> dict[str, Any]:
        """Analyze test coverage and produce metrics and findings."""
        source_files = [f for f in files if f.role == "source"]
        test_files = [f for f in files if f.role == "test"]

        source_lines_added = sum(f.lines_added for f in source_files)
        test_lines_added = sum(f.lines_added for f in test_files)

        test_ratio = round(test_lines_added / max(1, source_lines_added), 2)
        symbols = self.extract_source_symbols(source_files)

        # Collect all test added code
        test_code_corpus: list[str] = []
        for tf in test_files:
            for hunk in tf.hunks:
                test_code_corpus.extend(line_info.content for line_info in hunk.added_lines)
        test_corpus_str = "\n".join(test_code_corpus)

        has_assertions = bool(_ASSERT_PATTERNS.search(test_corpus_str))
        has_error_tests = bool(_ERROR_PATH_PATTERNS.search(test_corpus_str))

        # Per-symbol coverage mapping
        symbol_map: list[dict[str, Any]] = []
        tested_count = 0
        untested_count = 0
        partial_count = 0

        for sym, file_path, line_no in symbols:
            # Check if symbol is referenced in test files
            sym_pattern = re.compile(r"\b" + re.escape(sym) + r"\b")
            if not sym_pattern.search(test_corpus_str):
                status = "untested"
                untested_count += 1
            else:
                if has_assertions:
                    status = "tested"
                    tested_count += 1
                else:
                    status = "partially tested"
                    partial_count += 1

            symbol_map.append(
                {
                    "symbol": sym,
                    "file_path": file_path,
                    "line_number": line_no,
                    "status": status,
                }
            )

        total_symbols = len(symbols)
        symbol_pct = (
            round((tested_count / total_symbols * 100.0), 1) if total_symbols > 0 else 100.0
        )

        # Check external coverage report if present
        measured_coverage = None
        if coverage_report_path:
            measured_coverage = self.parse_coverage_report(coverage_report_path)

        # Generate Findings
        findings: list[Finding] = []

        # If pure docs/config change, no coverage findings needed
        if not source_files:
            return {
                "test_ratio": test_ratio,
                "tested_symbol_percent": symbol_pct,
                "symbol_map": symbol_map,
                "has_assertions": has_assertions,
                "has_error_tests": has_error_tests,
                "findings": findings,
                "coverage_mode": "measured" if measured_coverage else "estimated",
            }

        # Rule TST-UNTESTED-001: New business logic with zero tests
        untested_symbols = [s for s in symbol_map if s["status"] == "untested"]
        if untested_symbols:
            citation = self._get_citation("TST-UNTESTED-001")
            for item in untested_symbols:
                findings.append(
                    Finding(
                        id=Finding.generate_id(
                            Category.TEST_COVERAGE,
                            "TST-UNTESTED-001",
                            item["file_path"],
                            item["line_number"],
                        ),
                        category=Category.TEST_COVERAGE,
                        severity=Severity.HIGH,
                        title=f"Untested Public Function or Class '{item['symbol']}'",
                        description=(
                            f"New public declaration '{item['symbol']}' introduced in '{item['file_path']}' "
                            f"(line {item['line_number']}) has no corresponding test references in the diff."
                        ),
                        file_path=item["file_path"],
                        line_start=item["line_number"],
                        line_end=item["line_number"],
                        code_snippet=f"def {item['symbol']}(...)",
                        rule_id="TST-UNTESTED-001",
                        evidence_source=citation,
                        recommendation=f"Add unit tests for '{item['symbol']}' in a test file covering nominal and edge cases.",
                        confidence=1.0 if citation else 0.90,
                        reported_by=["test_coverage_agent"],
                    )
                )

        # Rule TST-PARTIAL-001: Partial test coverage without assertions
        partial_symbols = [s for s in symbol_map if s["status"] == "partially tested"]
        if partial_symbols:
            citation = self._get_citation("TST-PARTIAL-001")
            for item in partial_symbols:
                findings.append(
                    Finding(
                        id=Finding.generate_id(
                            Category.TEST_COVERAGE,
                            "TST-PARTIAL-001",
                            item["file_path"],
                            item["line_number"],
                        ),
                        category=Category.TEST_COVERAGE,
                        severity=Severity.MEDIUM,
                        title=f"Superficial Test Coverage for '{item['symbol']}'",
                        description=(
                            f"Function '{item['symbol']}' is referenced in tests but lacks assertion verifications "
                            "or exception checks."
                        ),
                        file_path=item["file_path"],
                        line_start=item["line_number"],
                        line_end=item["line_number"],
                        code_snippet=f"def {item['symbol']}(...)",
                        rule_id="TST-PARTIAL-001",
                        evidence_source=citation,
                        recommendation="Add explicit verification assertions (e.g. assert result == expected) to the test case.",
                        confidence=1.0 if citation else 0.90,
                        reported_by=["test_coverage_agent"],
                    )
                )

        # Rule TST-RATIO-001: Low test ratio on significant changes
        if source_lines_added > 30 and test_ratio < 0.30:
            citation = self._get_citation("TST-RATIO-001")
            findings.append(
                Finding(
                    id=Finding.generate_id(
                        Category.TEST_COVERAGE, "TST-RATIO-001", source_files[0].path, 1
                    ),
                    category=Category.TEST_COVERAGE,
                    severity=Severity.MEDIUM,
                    title=f"Inadequate Change Test Ratio ({test_ratio:.2f})",
                    description=(
                        f"Pull request adds {source_lines_added} production lines but only {test_lines_added} test lines "
                        f"(ratio {test_ratio:.2f} < 0.30 target)."
                    ),
                    file_path=source_files[0].path,
                    line_start=1,
                    rule_id="TST-RATIO-001",
                    evidence_source=citation,
                    recommendation="Increase test coverage to match the volume and complexity of the production change.",
                    confidence=1.0 if citation else 0.85,
                    reported_by=["test_coverage_agent"],
                )
            )

        return {
            "test_ratio": test_ratio,
            "tested_symbol_percent": symbol_pct,
            "symbol_map": symbol_map,
            "has_assertions": has_assertions,
            "has_error_tests": has_error_tests,
            "findings": findings,
            "coverage_mode": "measured" if measured_coverage else "estimated",
            "measured_coverage": measured_coverage,
        }
