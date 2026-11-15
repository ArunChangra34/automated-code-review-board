"""Streamlit Web UI for the Automated Code Review Board."""

from __future__ import annotations

import asyncio
from pathlib import Path

import streamlit as st

from config.settings import get_settings
from core.diff_loader import load_diff_from_stdin
from core.models import Severity
from core.orchestrator import ReviewOrchestrator
from reporting.json_report import generate_json_report
from reporting.markdown_report import generate_markdown_report

st.set_page_config(
    page_title="Automated Code Review Board",
    page_icon="🛡️",
    layout="wide",
)

st.title("🛡️ Automated Code Review Board")
st.caption("Multi-Agent Unified Diff Review System with Verified Patch Generation")

# Sidebar: Configuration & Input selection
st.sidebar.header("Review Configuration")
mode = st.sidebar.selectbox("Execution Mode", options=["offline", "llm"], index=0)
diff_source = st.sidebar.radio(
    "Diff Input Source",
    options=["Sample Diffs", "Upload Diff File", "Paste Unified Diff"],
    index=0,
)

samples_dir = Path("samples") / "diffs"
sample_files = sorted(samples_dir.glob("*.diff")) if samples_dir.exists() else []
selected_sample = None
uploaded_file = None
pasted_diff = ""

if diff_source == "Sample Diffs":
    if sample_files:
        sample_names = [f.name for f in sample_files]
        chosen_name = st.sidebar.selectbox("Choose a sample diff", sample_names, index=4)
        selected_sample = samples_dir / chosen_name
    else:
        st.sidebar.warning("No sample diff files found in samples/diffs/")
elif diff_source == "Upload Diff File":
    uploaded_file = st.sidebar.file_uploader(
        "Upload .diff or .patch", type=["diff", "patch", "txt"]
    )
else:
    pasted_diff = st.sidebar.text_area("Paste unified diff here", height=250)

run_button = st.sidebar.button(
    "🚀 Run Multi-Agent Review", type="primary", use_container_width=True
)

# Main area
raw_diff_text = ""
state = None

if selected_sample and selected_sample.exists():
    raw_diff_text = selected_sample.read_text(encoding="utf-8")
elif uploaded_file:
    raw_diff_text = uploaded_file.getvalue().decode("utf-8", errors="replace")
elif pasted_diff:
    raw_diff_text = pasted_diff

if raw_diff_text:
    with st.expander("📄 View Input Unified Diff", expanded=False):
        st.code(raw_diff_text, language="diff")

if run_button:
    if not raw_diff_text.strip():
        st.error("Please provide or select a unified diff before running the review.")
    else:
        settings = get_settings()
        settings.mode = mode

        with st.spinner(
            "Executing concurrent specialist agents (Diff, Style, Security, Coverage)..."
        ):
            state = load_diff_from_stdin(raw_diff_text)
            orchestrator = ReviewOrchestrator(settings=settings)
            state = asyncio.run(orchestrator.run_review(state))

        review = state.consolidated_review
        summary = state.summary
        patch = state.suggested_patch or (review.suggested_patch if review else None)

        if review:
            # 1. Prominent Recommendation Banner
            col_rec, col_score, col_findings = st.columns([2, 1, 1])
            with col_rec:
                if review.decision == "APPROVE":
                    st.success("### 🟢 RECOMMENDATION: APPROVE")
                else:
                    st.error("### 🔴 RECOMMENDATION: REQUEST CHANGES")
                st.write(f"**Why this decision:** {review.decision_reason}")

            with col_score:
                st.metric(
                    label="Merge-Risk Score",
                    value=f"{review.merge_risk_score}/100",
                    delta=(
                        "Passes Threshold" if review.decision == "APPROVE" else "Exceeds Tolerance"
                    ),
                    delta_color="normal" if review.decision == "APPROVE" else "inverse",
                )

            with col_findings:
                total_f = len(review.priority_order)
                crit_f = len(review.findings_by_severity.get(Severity.CRITICAL, []))
                st.metric(
                    label="Total Deduplicated Findings",
                    value=total_f,
                    delta=f"{crit_f} Critical",
                    delta_color="inverse" if crit_f > 0 else "off",
                )

            st.divider()

            # 2. Tabbed Detailed Analysis
            tab_findings, tab_patch, tab_coverage, tab_summary, tab_timeline, tab_export = st.tabs(
                [
                    "🔍 Review Findings",
                    "🛠️ Suggested Verified Fix",
                    "🧪 Test Coverage",
                    "📊 Change Summary",
                    "⏱️ Agent Timeline",
                    "📥 Export Reports",
                ]
            )

            # Tab 1: Findings by Severity
            with tab_findings:
                st.subheader("Prioritized Review Findings")
                if not review.priority_order:
                    st.info("Zero findings detected. Changeset meets all acceptance standards!")
                else:
                    for f in review.priority_order:
                        sev_badge = {
                            Severity.CRITICAL: "🔴 CRITICAL",
                            Severity.HIGH: "🟠 HIGH",
                            Severity.MEDIUM: "🟡 MEDIUM",
                            Severity.LOW: "🔵 LOW",
                            Severity.INFO: "⚪ INFO",
                        }.get(f.severity, f.severity.value)

                        corrob_str = (
                            f" • 🎯 Corroborated by {len(f.corroborated_by)} agents"
                            if len(f.corroborated_by) > 1
                            else ""
                        )
                        with st.expander(
                            f"Rank #{f.priority_rank} [{sev_badge}] {f.title} ({f.file_path or 'global'}){corrob_str}"
                        ):
                            st.write(f"**Explanation:** {f.description}")
                            if f.code_snippet:
                                st.code(f.code_snippet, language="python")
                            st.write(f"**Recommendation:** {f.recommendation}")
                            st.caption(
                                f"Rule: `{f.rule_id}` | Citation: `{f.evidence_source or 'Ungrounded'}` | Confidence: {int(f.confidence * 100)}%"
                            )

            # Tab 2: Suggested Verified Patch
            with tab_patch:
                st.subheader("Automated Fix for Highest-Severity Finding")
                if patch:
                    verif = patch.verification
                    if verif:
                        if verif.verdict == "VERIFIED":
                            st.success("### ✅ Patch Verification: VERIFIED (Safe to Merge)")
                        elif verif.verdict == "PARTIAL":
                            st.warning("### ⚠️ Patch Verification: PARTIAL (Minor Quality Notices)")
                        else:
                            st.error(
                                "### ❌ Patch Verification: REJECTED (Unsafe or Context Mismatch)"
                            )

                        st.write(f"**Target Finding:** `{patch.finding_id}` (`{patch.file_path}`)")
                        st.write(f"**Explanation:** {patch.explanation}")
                        st.code(patch.unified_diff, language="diff")

                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("Applies Cleanly", "Yes" if verif.applies_cleanly else "No")
                        c2.metric("Syntax Valid", "Yes" if verif.syntax_ok else "No")
                        c3.metric(
                            "Original Issue Resolved",
                            "Yes" if verif.original_finding_resolved else "No",
                        )
                        c4.metric("New Issues Introduced", len(verif.new_findings_introduced))

                        if patch.followups:
                            st.write("**Follow-up Actions Required:**")
                            for action in patch.followups:
                                st.write(f"- {action}")
                else:
                    st.info(
                        "No automated remediation patch required or synthesized for this changeset."
                    )

            # Tab 3: Test Coverage
            with tab_coverage:
                st.subheader("Test Adequacy & Symbol Coverage")
                try:
                    from plugins.coverage_plugin import CoveragePlugin

                    cov = CoveragePlugin().analyze_coverage(state.files)
                    st.write(
                        f"**Change Test Ratio:** `{cov.get('test_ratio', 0.0):.2f}` (test lines added / source lines added)"
                    )
                    symbol_map = cov.get("symbol_map", [])
                    if symbol_map:
                        st.table(symbol_map)
                    else:
                        st.info("No new public functions or classes declared in this changeset.")
                except Exception as exc:
                    st.warning(f"Could not compute coverage table: {exc}")

            # Tab 4: Change Summary
            with tab_summary:
                st.subheader("Diff Analysis & Risk Areas")
                if summary:
                    st.write(f"**Intent Summary:** {summary.intent_summary}")
                    st.write(
                        f"**Size Class:** `{summary.size_class}` (+{summary.lines_added} / -{summary.lines_removed} lines across {summary.total_files} files)"
                    )
                    st.write(
                        f"**Risk Areas Touched:** {', '.join(summary.risk_areas) if summary.risk_areas else 'None'}"
                    )
                    files_data = [
                        {
                            "Path": f.path,
                            "Change Type": f.change_type,
                            "+/-": f"+{f.lines_added} / -{f.lines_removed}",
                            "Role": f.role,
                            "Language": f.language,
                        }
                        for f in summary.files
                    ]
                    st.dataframe(files_data, use_container_width=True)

            # Tab 5: Agent Timeline
            with tab_timeline:
                st.subheader("Concurrent Agent Execution Timeline")
                timeline_rows = [
                    {
                        "Agent": t.agent_name,
                        "Event": t.event,
                        "Timestamp": t.timestamp,
                        "Duration": f"{t.duration_ms:.1f}ms" if t.duration_ms is not None else "-",
                        "Details": t.details or "-",
                    }
                    for t in state.timeline
                ]
                st.dataframe(timeline_rows, use_container_width=True)

            # Tab 6: Export Reports
            with tab_export:
                st.subheader("Download Generated Artifacts")
                md_content = generate_markdown_report(state, mode=mode)
                json_content = generate_json_report(state)

                c_md, c_json = st.columns(2)
                with c_md:
                    st.download_button(
                        label="📥 Download review.md",
                        data=md_content,
                        file_name=f"review_{state.change_id}.md",
                        mime="text/markdown",
                        use_container_width=True,
                    )
                with c_json:
                    st.download_button(
                        label="📥 Download review.json",
                        data=json_content,
                        file_name=f"review_{state.change_id}.json",
                        mime="application/json",
                        use_container_width=True,
                    )
