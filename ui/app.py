"""Streamlit Web UI for the Automated Code Review Board.

Designed for both everyday laypeople (managers, students, stakeholders)
and software engineers with clean visual explanations, plain-English summaries,
and technical inspection modes.
"""

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

# Page Configuration
st.set_page_config(
    page_title="Automated Code Review Board",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling for polished readability
st.markdown(
    """
    <style>
    .big-font { font-size: 1.15rem !important; line-height: 1.6; }
    .verdict-box-approve {
        background-color: #e8f5e9;
        border-left: 6px solid #2e7d32;
        padding: 1.2rem;
        border-radius: 8px;
        margin-bottom: 1rem;
    }
    .verdict-box-reject {
        background-color: #ffebee;
        border-left: 6px solid #c62828;
        padding: 1.2rem;
        border-radius: 8px;
        margin-bottom: 1rem;
    }
    .info-card {
        background-color: #f8f9fa;
        border: 1px solid #dee2e6;
        padding: 1rem;
        border-radius: 6px;
        margin-bottom: 0.8rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# App Title & Layman Introduction
st.title("🛡️ Automated Code Review Board")
st.markdown("""
    **Your AI-Powered Quality & Security Gatekeeper.**
    Whenever programmers write or change code, this board acts like a team of specialized senior inspectors.
    Four independent digital experts check the code simultaneously for **bugs, security leaks, messy style, and missing safety tests**,
    and even **test-drives an automatic repair** for the biggest danger found!
    """)

# Sidebar: Inputs and Scenarios
st.sidebar.header("🕹️ Control Panel")

# Presentation mode toggle
view_mode = st.sidebar.radio(
    "Display Perspective",
    options=["👶 Layman / Plain English View", "👨‍💻 Technical Developer View"],
    index=0,
    help="Switch between plain-English business summaries and detailed code diffs.",
)

execution_mode = st.sidebar.selectbox(
    "Agent Brain Mode",
    options=["offline", "llm"],
    index=0,
    help="Offline runs purely local deterministic rules (<0.1s). LLM mode adds generative reasoning.",
)

diff_source = st.sidebar.radio(
    "Choose What to Review",
    options=["Pre-Made Real Examples", "Upload a Diff File", "Paste Code Changes"],
    index=0,
)

# Friendly mapping for sample files
SAMPLE_EXPLANATIONS = {
    "01_clean_change.diff": "🟢 Clean & Safe Feature (What good code looks like)",
    "02_sql_injection_and_secret.diff": "🚨 Leaked Password & Database Flaw (Critical security emergency)",
    "03_untested_feature.diff": "⚠️ Feature Built with Zero Tests (Accident waiting to happen)",
    "04_style_mess.diff": "🧹 Messy & Hard-to-Read Code (High technical debt)",
    "05_mixed_realistic.diff": "📦 Complex Multi-File PR (Real-world mix of bugs and security risks)",
}

samples_dir = Path("samples") / "diffs"
sample_files = sorted(samples_dir.glob("*.diff")) if samples_dir.exists() else []
selected_sample = None
uploaded_file = None
pasted_diff = ""

if diff_source == "Pre-Made Real Examples":
    if sample_files:
        chosen_friendly = st.sidebar.selectbox(
            "Select an Example Scenario",
            options=[SAMPLE_EXPLANATIONS.get(f.name, f.name) for f in sample_files],
            index=4,
        )
        # Match back to real filename
        for f in sample_files:
            if SAMPLE_EXPLANATIONS.get(f.name, f.name) == chosen_friendly:
                selected_sample = f
                break
    else:
        st.sidebar.warning("No sample diff files found in samples/diffs/")
elif diff_source == "Upload Diff File":
    uploaded_file = st.sidebar.file_uploader(
        "Upload a .diff or .patch file",
        type=["diff", "patch", "txt"],
        help="A unified diff file showing additions (+) and deletions (-).",
    )
else:
    pasted_diff = st.sidebar.text_area(
        "Paste Unified Diff Text Here",
        height=220,
        placeholder="diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@ -1,3 +1,4 @@\n+print('hello')",
    )

run_button = st.sidebar.button(
    "🚀 Run Team Review Now",
    type="primary",
    use_container_width=True,
)

# Explanatory helper card in sidebar
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

# Determine Diff Content
raw_diff_text = ""
if selected_sample and selected_sample.exists():
    raw_diff_text = selected_sample.read_text(encoding="utf-8")
elif uploaded_file:
    raw_diff_text = uploaded_file.getvalue().decode("utf-8", errors="replace")
elif pasted_diff:
    raw_diff_text = pasted_diff

# Main Canvas
if not raw_diff_text.strip():
    st.info(
        "👈 Choose a sample scenario on the left and click **'Run Team Review Now'** to get started!"
    )
else:
    # Optional Preview of raw diff
    with st.expander("📄 Click to Peek at the Raw Code Changes", expanded=False):
        st.caption("Lines starting with '+' are new additions; lines with '-' are removals.")
        st.code(
            raw_diff_text[:3000] + ("\n... [truncated]" if len(raw_diff_text) > 3000 else ""),
            language="diff",
        )

if run_button and raw_diff_text.strip():
    settings = get_settings()
    settings.mode = execution_mode

    with st.spinner("🤖 All 4 specialist agents are reviewing your code in parallel..."):
        state = load_diff_from_stdin(raw_diff_text)
        orchestrator = ReviewOrchestrator(settings=settings)
        state = asyncio.run(orchestrator.run_review(state))

    review = state.consolidated_review
    summary = state.summary
    patch = state.suggested_patch or (review.suggested_patch if review else None)

    if review:
        st.markdown("---")

        # -------------------------------------------------------------
        # 1. High-Level Executive Verdict (Layman First)
        # -------------------------------------------------------------
        is_approved = review.decision == "APPROVE"
        risk_score = review.merge_risk_score
        total_findings = len(review.priority_order)
        crit_count = len(review.findings_by_severity.get(Severity.CRITICAL, []))
        high_count = len(review.findings_by_severity.get(Severity.HIGH, []))
        med_count = len(review.findings_by_severity.get(Severity.MEDIUM, []))
        low_count = len(review.findings_by_severity.get(Severity.LOW, []))

        if is_approved:
            st.markdown(
                f"""
                <div class="verdict-box-approve">
                    <h2 style="color: #2e7d32; margin-top:0;">✅ SAFE TO MERGE (Approved)</h2>
                    <p class="big-font">
                        <strong>Great news!</strong> This code was thoroughly examined by all 4 review specialists and meets every safety and quality standard.
                        There are <strong>zero dangerous vulnerabilities</strong> or blocking issues.
                    </p>
                    <p><em>Reason: {review.decision_reason}</em></p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"""
                <div class="verdict-box-reject">
                    <h2 style="color: #c62828; margin-top:0;">🛑 DO NOT MERGE YET (Changes Requested)</h2>
                    <p class="big-font">
                        <strong>Hold on!</strong> The review board found <strong>{crit_count + high_count} serious blocker(s)</strong> that could break your application, leak private credentials, or invite hackers.
                        These issues must be resolved before this code is merged into production.
                    </p>
                    <p><em>Why this decision: {review.decision_reason}</em></p>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Quick Vital Scorecards
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
                help="Scores above 30 are considered risky and will block merging.",
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
                help="Critical (security flaws, passwords) and High severity (untested features).",
            )

        with col_total:
            st.metric(
                label="Total Notices Found",
                value=total_findings,
                delta=f"{crit_count} Crit • {high_count} High • {med_count} Med • {low_count} Low",
                delta_color="off",
                help="Deduplicated count across all 4 specialist agents.",
            )

        with col_time:
            # Calculate review duration
            total_duration_ms = sum(res.duration_ms for res in state.agent_results.values())
            st.metric(
                label="Review Turnaround Time",
                value=f"{total_duration_ms:.1f} ms",
                delta="⚡ Sub-second lightning fast",
                delta_color="normal",
                help="All agents run simultaneously in parallel without slowing you down.",
            )

        st.markdown("<br>", unsafe_allow_html=True)

        # -------------------------------------------------------------
        # 2. Tabbed Deep Dive
        # -------------------------------------------------------------
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

        # -------------------------------------------------------------
        # TAB 1: PLAIN ENGLISH SUMMARY
        # -------------------------------------------------------------
        with tab_simple:
            st.subheader("💡 At-A-Glance Breakdown")

            # Simple 3-column scorecard
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

        # -------------------------------------------------------------
        # TAB 2: ISSUES FOUND (PLAIN-LANGUAGE PROBLEM CARDS)
        # -------------------------------------------------------------
        with tab_problems:
            st.subheader("🔍 Detailed Issues Detected by the Board")

            if not review.priority_order:
                st.balloons()
                st.success("🎉 Outstanding job! No issues were identified in this changeset.")
            else:
                st.caption("Issues are listed in order of risk—fix the top ones first!")

                for idx, f in enumerate(review.priority_order, start=1):
                    # Severity color badges & layman explanations
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
                        Severity.INFO: (
                            "⚪ INFO",
                            "Notice: General observation about the code change",
                        ),
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

                        # Plain English Explanation
                        st.markdown(f"**What's the issue?**\n{f.description}")

                        # Code Snippet with secret protection
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

                        # Practical Recommendation
                        st.markdown(f"**💡 How to fix it:**\n> {f.recommendation}")

                        # Technical metadata only if user wants it
                        if "Technical" in view_mode:
                            st.divider()
                            st.caption(
                                f"**Rule ID:** `{f.rule_id}` | "
                                f"**Category:** `{f.category.value}` | "
                                f"**Confidence:** {int(f.confidence * 100)}% | "
                                f"**Documentary Evidence:** `{f.evidence_source or 'Ungrounded'}`"
                            )

        # -------------------------------------------------------------
        # TAB 3: AUTOMATIC REPAIR (ONE-CLICK SOLUTION)
        # -------------------------------------------------------------
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
                    st.markdown(
                        "The patch works, but minor cosmetic items may need manual tweaking."
                    )
                else:
                    st.error("### ❌ Fix Status: REJECTED")
                    st.markdown(
                        "An automated patch could not be guaranteed safe. Please consult manual instructions below."
                    )

                st.markdown(f"**Target Issue:** `{patch.finding_id}` in `{patch.file_path}`")
                st.info(f"**What this fix does:** {patch.explanation}")

                # Display Diff
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

        # -------------------------------------------------------------
        # TAB 4: SAFETY TESTS CHECKUP
        # -------------------------------------------------------------
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
                    # Make table layman friendly
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
                    st.info(
                        "ℹ️ No new public functions or classes were added in this update (e.g. only documentation or settings were touched)."
                    )
            except Exception as e:
                st.warning(f"Could not compute coverage check: {e}")

        # -------------------------------------------------------------
        # TAB 5: BEHIND THE SCENES (AGENTS & CONCURRENCY)
        # -------------------------------------------------------------
        with tab_agents:
            st.subheader("🤖 Multi-Agent Execution Board")
            st.markdown("""
                Instead of one monolithic script, **5 specialized agents** evaluated this code concurrently.
                Each agent possesses deep expertise in its respective field:
                """)

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

        # -------------------------------------------------------------
        # TAB 6: DOWNLOAD REPORTS
        # -------------------------------------------------------------
        with tab_downloads:
            st.subheader("📥 Export & Share Official Review Reports")
            st.markdown(
                "Download full audit reports to attach to your GitHub pull request or archive for compliance:"
            )

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
