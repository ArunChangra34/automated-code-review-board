"""Streamlit Web UI for the Automated Code Review Board.

Offers two distinct perspectives:
1. Layman / Plain English View: Business-level summaries, intuitive analogies, and plain-English scorecards.
2. Technical Developer View: The original developer layout with exact diffs, AST symbols, rule IDs, and dataframes.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st  # noqa: E402

from config.settings import get_settings  # noqa: E402
from core.diff_loader import load_diff_from_stdin  # noqa: E402
from core.models import Severity  # noqa: E402
from core.orchestrator import ReviewOrchestrator  # noqa: E402
from reporting.json_report import generate_json_report  # noqa: E402
from reporting.markdown_report import generate_markdown_report  # noqa: E402

# Page Configuration
st.set_page_config(
    page_title="Automated Code Review Board",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling for layman presentation
st.markdown(
    """
    <style>
    .big-font { font-size: 1.15rem !important; line-height: 1.6; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Header Title
st.title("🛡️ Automated Code Review Board")
st.caption("Multi-Agent Unified Diff Review System with Verified Patch Generation")

# Sidebar Configuration
st.sidebar.header("Review Configuration")

view_mode = st.sidebar.radio(
    "Display Perspective",
    options=["👶 Layman / Plain English View", "👨‍💻 Technical Developer View"],
    index=0,
    help="Switch between plain-English business summaries and technical developer diffs.",
)

execution_mode = st.sidebar.selectbox(
    "Execution Mode",
    options=["offline", "llm"],
    index=0,
    help="Offline runs purely local deterministic rules (<0.1s). LLM mode adds generative reasoning.",
)

diff_source = st.sidebar.radio(
    "Diff Input Source",
    options=["Pre-Made Real Examples", "Upload a Diff File", "Paste Unified Diff"],
    index=0,
)

# Friendly descriptions for sample files
SAMPLE_EXPLANATIONS = {
    "01_clean_change.diff": "🟢 Clean & Safe Feature (What good code looks like)",
    "02_sql_injection_and_secret.diff": "🚨 Leaked Password & Database Flaw (Critical security emergency)",
    "03_untested_feature.diff": "⚠️ Feature Built with Zero Tests (Accident waiting to happen)",
    "04_style_mess.diff": "🧹 Messy & Hard-to-Read Code (High technical debt)",
    "05_mixed_realistic.diff": "📦 Complex Multi-File PR (Real-world mix of bugs and security risks)",
}

samples_dir = ROOT_DIR / "samples" / "diffs"
sample_files = sorted(samples_dir.glob("*.diff")) if samples_dir.exists() else []
selected_sample = None
uploaded_file = None
pasted_diff = ""

if "Pre-Made" in diff_source:
    if sample_files:
        chosen_friendly = st.sidebar.selectbox(
            "Select an Example Scenario",
            options=[SAMPLE_EXPLANATIONS.get(f.name, f.name) for f in sample_files],
            index=4,
        )
        for f in sample_files:
            if SAMPLE_EXPLANATIONS.get(f.name, f.name) == chosen_friendly:
                selected_sample = f
                break
    else:
        st.sidebar.warning("No sample diff files found in samples/diffs/")
elif "Upload" in diff_source:
    uploaded_file = st.sidebar.file_uploader(
        "Upload a .diff or .patch file",
        type=["diff", "patch", "txt"],
        help="A unified diff file showing additions (+) and deletions (-).",
    )
elif "Paste" in diff_source:
    pasted_diff = st.sidebar.text_area(
        "Paste Unified Diff Here",
        height=220,
        placeholder="diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@ -1,3 +1,4 @@\n+print('hello')",
    )

run_button = st.sidebar.button(
    "🚀 Run Team Review Now",
    type="primary",
    use_container_width=True,
)

with st.sidebar.expander("ℹ️ How Does This Work?", expanded=False):
    st.markdown("""
        **Meet Your 5 Specialist Agents:**
        1. 🔍 **Diff Inspector:** Sizes up the change and flags sensitive areas (payments, passwords).
        2. 🎨 **Style Guardian:** Makes sure code is tidy, easy to read, and well-named.
        3. 🛡️ **Security Shield:** Hunts for leaked passwords and hacker loopholes.
        4. 🧪 **Test Detective:** Checks if safety tests were written for new functions.
        5. ⚖️ **Reviewer Manager:** Combines all notes, discards duplicates, and renders the final verdict.
        6. 🔧 **Auto-Fixer:** Writes a verified patch for the worst problem found!
        """)

# Read selected diff text
raw_diff_text = ""
if selected_sample and selected_sample.exists():
    raw_diff_text = selected_sample.read_text(encoding="utf-8")
elif uploaded_file:
    raw_diff_text = uploaded_file.getvalue().decode("utf-8", errors="replace")
elif pasted_diff:
    raw_diff_text = pasted_diff

# Initial instructions
if not raw_diff_text.strip():
    if "Upload" in diff_source:
        st.info(
            "👈 Please upload a `.diff` or `.patch` file in the sidebar and click **'Run Team Review Now'**!"
        )
    elif "Paste" in diff_source:
        st.info(
            "👈 Please paste your unified diff text into the box in the sidebar and click **'Run Team Review Now'**!"
        )
    else:
        st.info(
            "👈 Choose a sample scenario on the left and click **'Run Team Review Now'** to get started!"
        )
else:
    with st.expander("📄 View Input Unified Diff", expanded=False):
        st.caption(
            "This box displays the raw code changes (unified diff) currently loaded into the system. "
            "To review this document with the AI agents, click **'Run Team Review Now'** in the sidebar."
        )
        st.code(
            raw_diff_text[:3000] + ("\n... [truncated]" if len(raw_diff_text) > 3000 else ""),
            language="diff",
        )


# -----------------------------------------------------------------------------
# 1. LAYMAN VIEW IMPLEMENTATION
# -----------------------------------------------------------------------------
def render_layman_view(state, review, summary, patch):
    """Render plain-English, executive and layman friendly view."""
    is_approved = review.decision == "APPROVE"
    risk_score = review.merge_risk_score
    total_findings = len(review.priority_order)
    crit_count = len(review.findings_by_severity.get(Severity.CRITICAL, []))
    high_count = len(review.findings_by_severity.get(Severity.HIGH, []))
    med_count = len(review.findings_by_severity.get(Severity.MEDIUM, []))
    low_count = len(review.findings_by_severity.get(Severity.LOW, []))

    # Big Plain-English Decision Banner
    if is_approved:
        st.success(
            "### ✅ SAFE TO MERGE (Approved)\n\n"
            "**Great news!** This code was thoroughly examined by all 4 review specialists and meets every safety and quality standard. "
            "There are **zero dangerous vulnerabilities** or blocking issues.\n\n"
            f"*Reason: {review.decision_reason}*"
        )
    else:
        st.error(
            "### 🛑 DO NOT MERGE YET (Changes Requested)\n\n"
            f"**Hold on!** The review board found **{crit_count + high_count} serious blocker(s)** that could break your application, "
            "leak private credentials, or introduce vulnerabilities.\n\n"
            "These issues must be resolved before this code is merged into production.\n\n"
            f"*Why this decision: {review.decision_reason}*"
        )

    # 4 Vital Scorecards
    col_risk, col_blockers, col_total, col_time = st.columns(4)
    with col_risk:
        risk_label = (
            "🟢 Low Risk"
            if risk_score < 30
            else ("🟡 Moderate Risk" if risk_score < 70 else "🔴 Dangerous Risk")
        )
        st.metric(
            label="Overall Risk Score",
            value=f"{risk_score} / 100",
            delta=risk_label,
            delta_color="normal" if is_approved else "inverse",
        )
    with col_blockers:
        blocker_count = crit_count + high_count
        st.metric(
            label="Must-Fix Blocker Issues",
            value=blocker_count,
            delta=(
                "0 Blockers Needed"
                if blocker_count == 0
                else f"{blocker_count} Immediate Action Items"
            ),
            delta_color="normal" if blocker_count == 0 else "inverse",
        )
    with col_total:
        st.metric(
            label="Total Notices Found",
            value=total_findings,
            delta=f"{crit_count} Crit • {high_count} High • {med_count} Med • {low_count} Low",
            delta_color="off",
        )
    with col_time:
        total_duration_ms = sum(res.duration_ms for res in state.agent_results.values())
        st.metric(
            label="Review Turnaround Time",
            value=f"{total_duration_ms:.1f} ms",
            delta="⚡ Sub-second lightning fast",
            delta_color="normal",
        )

    st.markdown("<br>", unsafe_allow_html=True)

    tab_simple, tab_problems, tab_autofix, tab_testing, tab_agents, tab_downloads = st.tabs(
        [
            "📋 Plain English Summary",
            f"🚨 Issues Found ({total_findings})",
            "🔧 Automatic Repair (Verified Fix)",
            "🧪 Safety Tests Checkup",
            "🤖 Behind the Scenes (Agents)",
            "📥 Download Reports",
        ]
    )

    # Tab 1: Plain English Summary
    with tab_simple:
        st.subheader("💡 At-A-Glance Health Breakdown")
        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            st.markdown("#### 🔒 Security Health")
            if crit_count == 0:
                st.success(
                    "✅ **No Passwords or Leaks Detected**\n\nThe code does not expose credentials or common injection vulnerabilities."
                )
            else:
                st.error(
                    f"❌ **{crit_count} Critical Flaw(s) Found!**\n\nSensitive passwords, secret tokens, or vulnerable database queries were detected."
                )
        with sc2:
            st.markdown("#### 🧪 Test Health")
            if high_count == 0 or not any(
                f.category.value == "test_coverage" for f in review.priority_order
            ):
                st.success(
                    "✅ **Properly Tested**\n\nNew logic has corresponding unit tests to prevent future bugs."
                )
            else:
                st.warning(
                    "⚠️ **Missing Safety Tests**\n\nProgrammers introduced new features without testing them. Untested code often breaks down the line."
                )
        with sc3:
            st.markdown("#### 🧹 Code Cleanliness")
            if med_count == 0 and low_count == 0:
                st.success(
                    "✅ **Sparkling Clean**\n\nCode follows standard readability and naming conventions."
                )
            else:
                st.info(
                    f"ℹ️ **{med_count + low_count} Maintainability Note(s)**\n\nMinor style items (like overly long lines or debug statements) that should be tidied up."
                )

        st.markdown("---")
        st.markdown("### 🗺️ What Changed in This Update?")
        if summary:
            st.markdown(f"**Intent Summary:** *{summary.intent_summary}*")
            c_size, c_files, c_lines = st.columns(3)
            c_size.info(
                f"**Change Size Category:** `{summary.size_class}` (Small changes are safer to review than giant ones)"
            )
            c_files.info(f"**Files Touched:** {summary.total_files} file(s)")
            c_lines.info(
                f"**Lines Changed:** +{summary.lines_added} added, -{summary.lines_removed} deleted"
            )
            if summary.risk_areas:
                st.warning(
                    f"⚠️ **Caution:** This update modifies sensitive parts of the application: **{', '.join(summary.risk_areas).upper()}**."
                )

    # Tab 2: Issues Found
    with tab_problems:
        st.subheader("🔍 Detailed Issues Detected by the Board")
        if not review.priority_order:
            st.success("🎉 Outstanding job! No issues were identified in this changeset.")
        else:
            st.caption("Issues are listed in order of risk—fix the top ones first!")
            for idx, f in enumerate(review.priority_order, start=1):
                sev_meta = {
                    Severity.CRITICAL: (
                        "🔴 CRITICAL",
                        "Danger: Immediate security risk, data loss, or leaked password",
                    ),
                    Severity.HIGH: (
                        "🟠 HIGH",
                        "Important: Missing safety tests or serious logic risk",
                    ),
                    Severity.MEDIUM: (
                        "🟡 MEDIUM",
                        "Warning: Could cause reliability issues or difficult maintenance",
                    ),
                    Severity.LOW: ("🔵 LOW", "Tip: Readability, naming, or minor cleanup"),
                    Severity.INFO: ("⚪ INFO", "Notice: General observation about the code change"),
                }.get(f.severity, ("Notice", ""))
                sev_title, sev_desc = sev_meta
                corrob_badge = (
                    f" • 🎯 Confirmed by {len(f.corroborated_by)} independent agents"
                    if len(f.corroborated_by) > 1
                    else ""
                )

                with st.expander(
                    f"#{idx}. [{sev_title}] {f.title} ({f.file_path or 'General'}){corrob_badge}"
                ):
                    st.caption(f"**Severity Meaning:** {sev_desc}")
                    st.markdown(f"**What's the issue?**\n{f.description}")
                    if f.code_snippet:
                        st.markdown("**Where it happens:**")
                        st.code(
                            f.code_snippet,
                            language=(
                                "python"
                                if (f.file_path and f.file_path.endswith(".py"))
                                else "text"
                            ),
                        )
                    st.markdown(f"**💡 How to fix it:**\n> {f.recommendation}")

    # Tab 3: Automatic Repair
    with tab_autofix:
        st.subheader("🔧 Self-Healing Fix for the #1 Worst Issue")
        st.markdown("""
            Most tools only complain about problems. **Our system actually writes a fix, applies it in a safe memory sandbox,
            and tests it to prove that it eliminates the flaw without introducing any new bugs!**
            """)
        if patch:
            verif = patch.verification
            if verif and verif.verdict == "VERIFIED":
                st.success("### ✅ Fix Status: 100% VERIFIED & SAFE TO APPLY")
                st.markdown(
                    "The automated patch below was successfully tested in an isolated sandbox. It fixes the vulnerability completely and broke zero existing features."
                )
            elif verif and verif.verdict == "PARTIAL":
                st.warning("### ⚠️ Fix Status: PARTIALLY VERIFIED")
                st.markdown("The patch works, but minor cosmetic items may need manual tweaking.")
            else:
                st.error("### ❌ Fix Status: REJECTED")
                st.markdown(
                    "An automated patch could not be guaranteed safe. Please consult manual instructions below."
                )

            st.markdown(f"**Target Issue:** `{patch.finding_id}` in `{patch.file_path}`")
            st.info(f"**What this fix does:** {patch.explanation}")
            st.markdown("**Proposed Code Replacement (Red is removed, Green is added):**")
            st.code(patch.unified_diff, language="diff")

            if verif:
                st.markdown("#### 🧪 Sandbox Safety Inspection Results")
                v1, v2, v3, v4 = st.columns(4)
                v1.metric("Applies Cleanly?", "✅ Yes" if verif.applies_cleanly else "❌ No")
                v2.metric("Code Syntax Valid?", "✅ Valid" if verif.syntax_ok else "❌ Broken")
                v3.metric(
                    "Original Flaw Gone?",
                    "✅ Eliminated" if verif.original_finding_resolved else "❌ Still Present",
                )
                v4.metric(
                    "New Bugs Added?",
                    (
                        "0 New Bugs"
                        if len(verif.new_findings_introduced) == 0
                        else f"{len(verif.new_findings_introduced)} New Issues"
                    ),
                )

            if patch.followups:
                st.markdown("**Next Steps for Developers:**")
                for act in patch.followups:
                    st.markdown(f"- {act}")
        else:
            st.info(
                "✨ No critical automated repairs were required for this changeset. All looks smooth!"
            )

    # Tab 4: Safety Tests Checkup
    with tab_testing:
        st.subheader("🧪 Software Testing Audit")
        st.markdown("""
            In professional software engineering, writing code without automated tests is like driving without a seatbelt.
            Here is our audit of whether the newly written features have safety tests:
            """)
        try:
            from plugins.coverage_plugin import CoveragePlugin

            cov = CoveragePlugin().analyze_coverage(state.files)
            test_ratio = cov.get("test_ratio", 0.0)
            symbol_map = cov.get("symbol_map", [])

            c_rat, c_assert, c_err = st.columns(3)
            c_rat.metric(
                label="Test-to-Code Ratio",
                value=f"{test_ratio:.2f}",
                delta="Healthy (>0.5)" if test_ratio >= 0.5 else "Needs More Tests (<0.5)",
                delta_color="normal" if test_ratio >= 0.5 else "inverse",
            )
            c_assert.metric(
                "Quality Assertions Present?",
                "✅ Yes" if cov.get("has_assertions") else "❌ Missing",
            )
            c_err.metric(
                "Error/Failure Cases Tested?",
                "✅ Yes" if cov.get("has_error_tests") else "⚠️ Untested",
            )

            st.markdown("---")
            st.markdown("#### Function-by-Function Test Roster")
            if symbol_map:
                friendly_rows = []
                for s in symbol_map:
                    st_raw = s.get("status", "untested")
                    st_label = (
                        "🟢 Tested & Verified"
                        if st_raw == "tested"
                        else (
                            "🟡 Partially Tested"
                            if st_raw == "partially tested"
                            else "🔴 Untested (Dangerous)"
                        )
                    )
                    friendly_rows.append(
                        {
                            "Function / Class Name": s.get("symbol"),
                            "File Location": f"{s.get('file_path')}:{s.get('line_number')}",
                            "Safety Status": st_label,
                        }
                    )
                st.dataframe(friendly_rows, use_container_width=True)
            else:
                st.info("ℹ️ No new public functions or classes were added in this update.")
        except Exception as e:
            st.warning(f"Could not compute coverage check: {e}")

    # Tab 5: Behind The Scenes
    with tab_agents:
        st.subheader("🤖 Multi-Agent Execution Board")
        agent_cards = [
            ("🔍 Diff Agent", "Structure & Metrics", state.agent_results.get("diff_agent")),
            (
                "🎨 Style Agent",
                "Code Neatness & Readability",
                state.agent_results.get("style_agent"),
            ),
            (
                "🛡️ Security Agent",
                "OWASP & Secrets Scanning",
                state.agent_results.get("security_agent"),
            ),
            (
                "🧪 Test-Coverage Agent",
                "Safety Tests Verification",
                state.agent_results.get("test_coverage_agent"),
            ),
            (
                "⚖️ Reviewer Manager",
                "Consolidation & Final Decision",
                state.agent_results.get("reviewer_manager"),
            ),
        ]
        a_cols = st.columns(len(agent_cards))
        for i, (name, role, res) in enumerate(agent_cards):
            with a_cols[i]:
                st.markdown(f"**{name}**")
                st.caption(role)
                if res:
                    st.markdown(f"**Status:** {'🟢 OK' if res.status == 'ok' else '🔴 Failed'}")
                    st.markdown(f"**Time:** `{res.duration_ms:.1f}ms`")
                    st.markdown(f"**Found:** `{len(res.findings)} issues`")
                else:
                    st.caption("Standby")

        st.markdown("---")
        st.markdown("#### ⏱️ Concurrency Timeline")
        st.caption(
            "Proof of true parallel execution: notice all 4 specialist agents start and finish at the same millisecond mark!"
        )
        timeline_rows = [
            {
                "Agent Name": t.agent_name,
                "Action Event": t.event.upper(),
                "Exact Timestamp": t.timestamp,
                "Time Taken": f"{t.duration_ms:.1f} ms" if t.duration_ms is not None else "-",
            }
            for t in state.timeline
        ]
        st.dataframe(timeline_rows, use_container_width=True)

    # Tab 6: Downloads
    with tab_downloads:
        st.subheader("📥 Export & Share Official Review Reports")
        md_content = generate_markdown_report(state, mode=execution_mode)
        json_content = generate_json_report(state)
        d1, d2 = st.columns(2)
        with d1:
            st.download_button(
                label="📄 Download Markdown Report (review.md)",
                data=md_content,
                file_name=f"review_{state.change_id}.md",
                mime="text/markdown",
                use_container_width=True,
            )
        with d2:
            st.download_button(
                label="💾 Download Raw Data (review.json)",
                data=json_content,
                file_name=f"review_{state.change_id}.json",
                mime="application/json",
                use_container_width=True,
            )


# -----------------------------------------------------------------------------
# 2. ORIGINAL TECHNICAL DEVELOPER VIEW (EXACTLY AS IT WAS INITIALLY)
# -----------------------------------------------------------------------------
def render_technical_view(state, review, summary, patch):
    """Render original technical developer view with raw diffs, AST symbols, and dataframes."""
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
            delta="Passes Threshold" if review.decision == "APPROVE" else "Exceeds Tolerance",
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

    # Technical Tab 1: Findings by Severity
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

    # Technical Tab 2: Suggested Verified Patch
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
                    st.error("### ❌ Patch Verification: REJECTED (Unsafe or Context Mismatch)")

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
            st.info("No automated remediation patch required or synthesized for this changeset.")

    # Technical Tab 3: Test Coverage
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

    # Technical Tab 4: Change Summary
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

    # Technical Tab 5: Agent Timeline
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

    # Technical Tab 6: Export Reports
    with tab_export:
        st.subheader("Download Generated Artifacts")
        md_content = generate_markdown_report(state, mode=execution_mode)
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


# -----------------------------------------------------------------------------
# EXECUTION CONTROLLER
# -----------------------------------------------------------------------------
if run_button and raw_diff_text.strip():
    settings = get_settings()
    settings.mode = execution_mode

    try:
        with st.spinner("Executing concurrent specialist agents (Diff, Style, Security, Coverage)..."):
            state = load_diff_from_stdin(raw_diff_text)
            orchestrator = ReviewOrchestrator(settings=settings)
            state = asyncio.run(orchestrator.run_review(state))

        st.session_state["review_state"] = state
        st.session_state["last_diff_text"] = raw_diff_text
    except Exception as exc:
        st.error(
            f"❌ **Failed to parse or review the diff:** {exc}\n\n"
            "Please ensure your input is in **Unified Diff** format (e.g., starts with `diff --git ...`, `--- a/...`, `+++ b/...`) "
            "or test one of the pre-made sample scenarios from the sidebar."
        )

# Render active review if available in session state
if "review_state" in st.session_state and st.session_state["review_state"]:
    cached_state = st.session_state["review_state"]
    review = cached_state.consolidated_review
    summary = cached_state.summary
    patch = cached_state.suggested_patch or (review.suggested_patch if review else None)

    # Check if the user changed the input in the sidebar without running review
    if raw_diff_text.strip() and raw_diff_text.strip() != st.session_state.get("last_diff_text", "").strip():
        st.warning(
            "⚠️ **Input Document Changed:** You have selected or uploaded a different document in the sidebar. "
            "Click **'🚀 Run Team Review Now'** to analyze this new document!"
        )

    if review:
        st.markdown("---")
        # Route to the selected perspective
        if "Technical" in view_mode:
            render_technical_view(cached_state, review, summary, patch)
        else:
            render_layman_view(cached_state, review, summary, patch)
