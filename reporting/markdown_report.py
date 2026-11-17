"""Markdown report generator for Automated Code Review Board."""

from __future__ import annotations

from typing import Any

from core.models import Finding, FixSuggestion, Severity
from core.state import ChangeState
from plugins.coverage_plugin import CoveragePlugin


def generate_markdown_report(state: ChangeState, mode: str = "offline") -> str:
    """Generate a comprehensive, human-readable review.md report following spec section 10."""
    review = state.consolidated_review
    summary = state.summary
    patch = state.suggested_patch or (review.suggested_patch if review else None)
    fix_suggestions: list[FixSuggestion] = state.fix_suggestions

    # 1. Header
    lines: list[str] = [
        "# Automated Code Review Board Report",
        "",
        f"- **Change ID:** `{state.change_id}`",
        f"- **Timestamp:** {state.submitted_at}",
        f"- **Review Mode:** `{mode}`",
        f"- **Source:** `{state.source}`",
        "",
        "---",
        "",
    ]

    # 2. Merge Recommendation Banner
    lines.append("## Merge Recommendation")
    lines.append("")
    if review:
        if review.decision == "APPROVE":
            lines.append("> ### 🟢 **RECOMMENDATION: APPROVE**")
        else:
            lines.append("> ### 🔴 **RECOMMENDATION: REQUEST CHANGES**")
        lines.append(f"> **Merge-Risk Score:** {review.merge_risk_score}/100")
        lines.append(">")
        lines.append(f"> **Why this decision:** {review.decision_reason}")
    else:
        lines.append("> **Status:** Review data incomplete or unavailable.")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 3. Change Summary (from Diff Agent)
    lines.append("## Change Summary")
    lines.append("")
    if summary:
        lines.append(f"**Intent:** {summary.intent_summary}")
        lines.append("")
        lines.append(
            f"- **Size Class:** `{summary.size_class}` ({summary.lines_added} lines added, "
            f"{summary.lines_removed} lines removed across {summary.total_files} file(s))"
        )
        risk_str = ", ".join(summary.risk_areas) if summary.risk_areas else "None detected"
        lines.append(f"- **Detected Risk Areas:** {risk_str}")
        lines.append("")
        lines.append("### Files Touched")
        lines.append("")
        lines.append("| File Path | Type | + / - | Role | Language |")
        lines.append("| :--- | :--- | :--- | :--- | :--- |")
        for f in summary.files:
            diff_stat = f"+{f.lines_added} / -{f.lines_removed}"
            lines.append(
                f"| `{f.path}` | {f.change_type} | {diff_stat} | {f.role} | {f.language} |"
            )
        lines.append("")
    else:
        lines.append("*No change summary available.*")
        lines.append("")
    lines.append("---")
    lines.append("")

    # 4. Findings by Severity
    lines.append("## Findings by Severity")
    lines.append("")
    severity_order = [
        Severity.CRITICAL,
        Severity.HIGH,
        Severity.MEDIUM,
        Severity.LOW,
        Severity.INFO,
    ]

    findings_by_sev: dict[Severity, list[Finding]] = (
        review.findings_by_severity if review else {s: [] for s in severity_order}
    )

    for sev in severity_order:
        sev_findings = findings_by_sev.get(sev, [])
        lines.append(f"### {sev.value} ({len(sev_findings)})")
        lines.append("")
        if not sev_findings:
            lines.append("*None*")
            lines.append("")
            continue

        for finding in sev_findings:
            rank_display = f"Rank #{finding.priority_rank}" if finding.priority_rank else "Unranked"
            lines.append(f"#### {rank_display} [{finding.severity.value}]: {finding.title}")
            lines.append("")
            lines.append(f"- **Category:** `{finding.category.value}`")
            loc = (
                f"`{finding.file_path}:{finding.line_start}-{finding.line_end}`"
                if finding.file_path and finding.line_start
                else (f"`{finding.file_path}`" if finding.file_path else "Global")
            )
            lines.append(f"- **Location:** {loc}")
            lines.append(f"- **Rule ID:** `{finding.rule_id}`")
            citation = (
                f"`{finding.evidence_source}`"
                if finding.evidence_source
                else "⚠️ *Ungrounded (no documentary citation found)*"
            )
            lines.append(f"- **Evidence Citation:** {citation}")
            lines.append(f"- **Confidence:** {int(finding.confidence * 100)}%")
            reported = ", ".join(finding.reported_by) if finding.reported_by else "unknown"
            lines.append(f"- **Reported By:** {reported}")
            if len(finding.corroborated_by) > 1:
                corrob_agents = ", ".join(finding.corroborated_by)
                lines.append(
                    f"- **Corroboration:** 🎯 *Corroborated by {len(finding.corroborated_by)} agents ({corrob_agents})*"
                )
            lines.append("")
            lines.append(f"**Explanation:** {finding.description}")
            lines.append("")
            if finding.code_snippet:
                lines.append("```python")
                lines.append(finding.code_snippet)
                lines.append("```")
                lines.append("")
            lines.append(f"**Recommendation:** {finding.recommendation}")
            lines.append("")

    lines.append("---")
    lines.append("")

    # 5. Priority Order (Fix First)
    lines.append("## Priority Order (Fix First)")
    lines.append("")
    if review and review.priority_order:
        lines.append("Findings ranked by risk severity, multi-agent corroboration, and confidence:")
        lines.append("")
        for finding in review.priority_order:
            loc = (
                f" ({finding.file_path}:{finding.line_start})"
                if finding.file_path and finding.line_start
                else ""
            )
            corrob_badge = " [🎯 Corroborated]" if len(finding.corroborated_by) > 1 else ""
            lines.append(
                f"{finding.priority_rank}. **[{finding.severity.value}]** `{finding.rule_id}`: {finding.title}{loc}{corrob_badge}"
            )
        lines.append("")
    else:
        lines.append("*No issues identified.*")
        lines.append("")
    lines.append("---")
    lines.append("")

    # 6. Test Coverage Map
    lines.append("## Test Coverage Map")
    lines.append("")
    coverage_analysis: dict[str, Any] = {}
    try:
        cov_plugin = CoveragePlugin()
        coverage_analysis = cov_plugin.analyze_coverage(state.files)
    except Exception:
        coverage_analysis = {}

    test_ratio = coverage_analysis.get("test_ratio", 0.0)
    has_asserts = coverage_analysis.get("has_assertions", False)
    has_error_tests = coverage_analysis.get("has_error_tests", False)
    symbol_map = coverage_analysis.get("symbol_map", [])

    lines.append(
        f"- **Change Test Ratio:** {test_ratio:.2f} (test lines added / source lines added)"
    )
    lines.append(f"- **Assertion Quality:** {'✅ Present' if has_asserts else '❌ None detected'}")
    lines.append(
        f"- **Error Path Tests:** {'✅ Present' if has_error_tests else '⚠️ None detected'}"
    )
    lines.append("")

    if symbol_map:
        lines.append("| Symbol | Declared In | Status |")
        lines.append("| :--- | :--- | :--- |")
        for sym_info in symbol_map:
            sym_name = sym_info.get("symbol", "")
            fpath = sym_info.get("file_path", "")
            lno = sym_info.get("line_number", "")
            status = sym_info.get("status", "untested")
            if status == "tested":
                status_icon = "🟢 Tested"
            elif status == "partially tested":
                status_icon = "🟡 Partially Tested"
            else:
                status_icon = "🔴 Untested"
            lines.append(f"| `{sym_name}` | `{fpath}:{lno}` | {status_icon} |")
        lines.append("")
    else:
        lines.append("*No new public functions or classes introduced in this change.*")
        lines.append("")
    lines.append("---")
    lines.append("")

    # 7. Suggested Fix for Top Finding (Fix-Suggestion Agent)
    lines.append("## Suggested Fix for Top Finding")
    lines.append("")
    if patch:
        lines.append(f"**Target Finding:** `{patch.finding_id}` (`{patch.file_path}`)")
        lines.append("")
        lines.append(f"**Explanation:** {patch.explanation}")
        lines.append("")
        lines.append("```diff")
        lines.append(patch.unified_diff)
        lines.append("```")
        lines.append("")

        if patch.new_imports:
            lines.append(
                f"**Required New Imports:** {', '.join(f'`{imp}`' for imp in patch.new_imports)}"
            )
            lines.append("")

        if patch.followups:
            lines.append("**Follow-up Actions:**")
            for action in patch.followups:
                lines.append(f"- {action}")
            lines.append("")

        # Verification result
        verif = patch.verification
        if verif:
            verdict_badge = {
                "VERIFIED": "🟢 **VERIFIED**",
                "PARTIAL": "🟡 **PARTIAL**",
                "REJECTED": "🔴 **REJECTED**",
            }.get(verif.verdict, verif.verdict)

            lines.append("### Automated Patch Verification Result")
            lines.append("")
            lines.append(f"- **Verdict:** {verdict_badge}")
            lines.append(f"- **Applies Cleanly:** {'✅ Yes' if verif.applies_cleanly else '❌ No'}")
            lines.append(f"- **Syntax Valid:** {'✅ Yes' if verif.syntax_ok else '❌ No'}")
            lines.append(
                f"- **Original Issue Resolved:** {'✅ Yes' if verif.original_finding_resolved else '❌ No'}"
            )
            intro_count = len(verif.new_findings_introduced)
            lines.append(
                f"- **New Issues Introduced:** {'0 (None)' if intro_count == 0 else f'⚠️ {intro_count} issue(s)'}"
            )
            if verif.details:
                lines.append(f"- **Verification Notes:** {verif.details}")
            lines.append("")
    else:
        lines.append("*No automated fix required or suggested for this changeset.*")
        lines.append("")
    lines.append("---")
    lines.append("")

    # 7b. Per-Finding Fix Suggestions (LLM-assisted)
    lines.append("## Fix Suggestions (LLM-assisted)")
    lines.append("")
    if fix_suggestions:
        lines.append(
            f"The following {len(fix_suggestions)} fix suggestion(s) were generated and verified:"
        )
        lines.append("")
        for sug in fix_suggestions:
            verdict_badge = ""
            if sug.verification:
                verdict_badge = {
                    "VERIFIED": " 🟢 **VERIFIED**",
                    "PARTIAL": " 🟡 **PARTIAL**",
                    "REJECTED": " 🔴 **REJECTED**",
                }.get(sug.verification.verdict, "")
            elif sug.kind == "new_file":
                verdict_badge = " 🔵 *syntax-checked*"
            elif sug.kind == "manual":
                verdict_badge = " ⚪ *manual guidance*"

            loc = (
                f"`{sug.file_path}:{sug.line_start}-{sug.line_end}`"
                if sug.line_start
                else f"`{sug.file_path}`"
            )
            lines.append(
                f"### Rank #{fix_suggestions.index(sug) + 1} `{sug.rule_id}` [{sug.severity.value}] — {loc}{verdict_badge}"
            )
            lines.append("")
            lines.append(f"**Kind:** `{sug.kind}` | **Source:** `{sug.source}`")
            lines.append("")
            lines.append(f"**Explanation:** {sug.explanation}")
            lines.append("")
            if sug.unified_diff:
                lines.append("```diff")
                lines.append(sug.unified_diff)
                lines.append("```")
                lines.append("")
            if sug.new_imports:
                lines.append(
                    f"**Required New Imports:** {', '.join(f'`{i}`' for i in sug.new_imports)}"
                )
                lines.append("")
            if sug.followups:
                lines.append("**Follow-up Actions:**")
                for action in sug.followups:
                    lines.append(f"- {action}")
                lines.append("")
            if sug.note:
                lines.append(f"*Note: {sug.note}*")
                lines.append("")
    else:
        # Explain why there are no suggestions
        if mode == "offline":
            lines.append(
                "> Fix suggestions are available in LLM mode (`--mode llm` with `CRB_LLM_API_KEY` set). "
                "In offline mode only the template patch for the top finding is produced "
                "(when `CRB_FIX_SUGGESTIONS=always`)."
            )
        else:
            agent_res = state.agent_results.get("fix_suggestion_agent")
            if agent_res and agent_res.status == "degraded":
                lines.append(
                    f"> LLM fix generation was attempted but all calls failed: {agent_res.error or 'unknown error'}."
                )
            else:
                lines.append(
                    "> No LLM fix suggestions were generated for this changeset "
                    "(no eligible findings or agent not run)."
                )
        lines.append("")
    lines.append("---")
    lines.append("")

    # 8. Agent Execution Report
    lines.append("## Agent Execution Report")
    lines.append("")
    lines.append("| Agent | Category | Status | Duration (ms) | Findings Count | Notes |")
    lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
    for agent_name, result in sorted(state.agent_results.items()):
        status_icon = {
            "ok": "🟢 ok",
            "degraded": "🟡 degraded",
            "failed": "🔴 failed",
            "timeout": "⏱️ timeout",
        }.get(result.status, result.status)
        agent_cat = result.findings[0].category.value if result.findings else "general"
        notes = result.error or ("LLM-augmented" if result.mode == "llm" else "Deterministic")
        lines.append(
            f"| `{agent_name}` | {agent_cat} | {status_icon} | {result.duration_ms:.1f}ms | {len(result.findings)} | {notes} |"
        )
    lines.append("")

    lines.append("### Concurrent Execution Timeline")
    lines.append("")
    lines.append("| Timestamp | Agent | Event | Duration (ms) | Details |")
    lines.append("| :--- | :--- | :--- | :--- | :--- |")
    for event in state.timeline:
        dur = f"{event.duration_ms:.1f}ms" if event.duration_ms is not None else "-"
        detail = event.details or "-"
        lines.append(
            f"| {event.timestamp} | `{event.agent_name}` | {event.event} | {dur} | {detail} |"
        )
    lines.append("")
    lines.append("---")
    lines.append("")

    # 9. Statistics
    lines.append("## Statistics")
    lines.append("")
    if review and review.stats:
        stats = review.stats
        lines.append(f"- **Total Deduplicated Findings:** {stats.get('total_findings', 0)}")
        lines.append(f"- **Duplicate Findings Merged:** {stats.get('duplicates_removed', 0)}")
        lines.append(f"- **Corroborated Findings:** {stats.get('corroborated_findings', 0)}")
        lines.append("")
        lines.append("### Findings by Category")
        lines.append("")
        for cat_name, cnt in stats.get("counts_by_category", {}).items():
            lines.append(f"- `{cat_name}`: {cnt}")
        lines.append("")
        lines.append("### Findings by Severity")
        lines.append("")
        for sev_name, cnt in stats.get("counts_by_severity", {}).items():
            lines.append(f"- `{sev_name}`: {cnt}")
        lines.append("")

    return "\n".join(lines)
