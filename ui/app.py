"""Streamlit Web UI for the Automated Code Review Board.

Offers two distinct perspectives:
1. Executive Summary View: High-level risk score, policy verdicts, and health breakdown.
2. Technical Developer View: In-depth developer layout with diffs, AST symbols, rule IDs, and dataframes.
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
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------------------------------------------------------
# THEME CONFIGURATION (LIGHT & DARK MODES)
# -----------------------------------------------------------------------------
if "theme_mode" not in st.session_state:
    st.session_state["theme_mode"] = "Dark"

theme_choice = st.sidebar.radio(
    "Interface Theme",
    options=["Dark", "Light"],
    index=0 if st.session_state["theme_mode"] == "Dark" else 1,
    horizontal=True,
)
st.session_state["theme_mode"] = theme_choice
is_dark = theme_choice == "Dark"

# Dynamic Palette
if is_dark:
    bg_app = "#0B0F19"
    bg_surface = "#111827"
    border_subtle = "#1F293D"
    border_focus = "#38BDF8"
    text_primary = "#F8FAFC"
    text_secondary = "#94A3B8"
    tag_bg = "#1E293B"
    btn_bg = "#38BDF8"
    btn_text = "#0B0F19"
    rec_approve_bg = "#032B20"
    rec_approve_border = "#059669"
    rec_approve_badge = "#064E3B"
    rec_approve_text = "#34D399"
    rec_changes_bg = "#380D12"
    rec_changes_border = "#DC2626"
    rec_changes_badge = "#7F1D1D"
    rec_changes_text = "#F87171"
    badge_crit_bg = "#450A0A"
    badge_crit_text = "#FCA5A5"
    badge_crit_border = "#7F1D1D"
    badge_high_bg = "#451A03"
    badge_high_text = "#FCD34D"
    badge_high_border = "#78350F"
    badge_med_bg = "#422006"
    badge_med_text = "#FDE047"
    badge_med_border = "#713F12"
    badge_low_bg = "#172554"
    badge_low_text = "#93C5FD"
    badge_low_border = "#1E3A8A"
else:
    bg_app = "#FAFAFA"
    bg_surface = "#FFFFFF"
    border_subtle = "#E2E8F0"
    border_focus = "#0F172A"
    text_primary = "#0F172A"
    text_secondary = "#64748B"
    tag_bg = "#F1F5F9"
    btn_bg = "#0F172A"
    btn_text = "#FFFFFF"
    rec_approve_bg = "#FFFFFF"
    rec_approve_border = "#A7F3D0"
    rec_approve_badge = "#ECFDF5"
    rec_approve_text = "#047857"
    rec_changes_bg = "#FFFFFF"
    rec_changes_border = "#FECACA"
    rec_changes_badge = "#FEF2F2"
    rec_changes_text = "#B91C1C"
    badge_crit_bg = "#FEF2F2"
    badge_crit_text = "#DC2626"
    badge_crit_border = "#FECACA"
    badge_high_bg = "#FFFBEB"
    badge_high_text = "#D97706"
    badge_high_border = "#FDE68A"
    badge_med_bg = "#FEFCE8"
    badge_med_text = "#CA8A04"
    badge_med_border = "#FEF08A"
    badge_low_bg = "#EFF6FF"
    badge_low_text = "#2563EB"
    badge_low_border = "#BFDBFE"

st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    /* Typography */
    .stMarkdown, .stMarkdown p, h1, h2, h3, h4, h5, h6,
    .tva-navbar, .intake-header, .intake-card,
    .rec-card-approve, .rec-card-changes {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }}

    /* Base App Theme */
    .stApp {{
        background-color: {bg_app} !important;
        color: {text_primary} !important;
    }}
    header[data-testid="stHeader"] {{
        background-color: {bg_app} !important;
    }}
    .main .block-container {{
        padding-top: 1.5rem !important;
        padding-bottom: 4rem !important;
        max-width: 1180px !important;
    }}

    /* Preserve Icon Font Ligatures */
    [data-testid="stIconMaterial"],
    [class*="material-symbols"],
    [class*="material-icons"],
    span[data-testid*="Icon"] {{
        font-family: 'Material Symbols Rounded', 'Material Symbols Outlined', 'Material Icons' !important;
    }}

    /* Sidebar */
    section[data-testid="stSidebar"] {{
        background-color: {bg_surface} !important;
        border-right: 1px solid {border_subtle} !important;
    }}
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span:not([data-testid="stIconMaterial"]) {{
        color: {text_primary} !important;
    }}
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {{
        font-weight: 600 !important;
        color: {text_secondary} !important;
        font-size: 13px !important;
    }}

    /* Top Navigation Bar */
    .tva-navbar {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 12px 24px;
        background: {bg_surface};
        border: 1px solid {border_subtle};
        border-radius: 12px;
        margin-bottom: 2rem;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
    }}
    .tva-brand {{
        display: flex;
        align-items: center;
        gap: 8px;
        font-weight: 700;
        font-size: 14px;
        letter-spacing: -0.02em;
        color: {text_primary};
    }}
    .tva-brand-tag {{
        font-weight: 400;
        color: {text_secondary};
        font-size: 13px;
        margin-left: 2px;
    }}
    .tva-nav-links {{
        display: flex;
        align-items: center;
        gap: 20px;
        font-size: 13px;
        font-weight: 500;
        color: {text_secondary};
    }}
    .tva-nav-links span.active {{
        color: {text_primary};
        font-weight: 600;
    }}
    .tva-status-pill {{
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 3px 10px;
        border-radius: 9999px;
        background: {tag_bg};
        color: {text_primary};
        font-size: 12px;
        font-weight: 500;
    }}
    .tva-status-dot {{
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background: #10B981;
    }}

    /* Header Title */
    .intake-header {{
        margin-bottom: 20px;
    }}
    .intake-title {{
        font-size: 30px;
        font-weight: 700;
        letter-spacing: -0.03em;
        color: {text_primary};
        margin-bottom: 6px;
    }}
    .intake-subtitle {{
        font-size: 14px;
        color: {text_secondary};
        line-height: 1.5;
        max-width: 780px;
    }}
    .code-pill {{
        background: {tag_bg};
        border: 1px solid {border_subtle};
        padding: 2px 6px;
        border-radius: 4px;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace !important;
        font-size: 12px;
        color: {text_primary};
    }}

    /* Central Intake Card */
    .intake-card {{
        background: {bg_surface};
        border: 1px solid {border_subtle};
        border-radius: 16px;
        box-shadow: 0 10px 30px -5px rgba(0, 0, 0, 0.1);
        padding: 22px 26px;
        margin-bottom: 24px;
    }}
    .intake-card-header {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-bottom: 1px solid {border_subtle};
        padding-bottom: 12px;
        margin-bottom: 16px;
    }}
    .intake-tag {{
        display: inline-flex;
        align-items: center;
        gap: 6px;
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: {text_secondary};
    }}
    .intake-dot {{
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background: #0EA5E9;
    }}

    /* Expanders */
    [data-testid="stExpander"] {{
        background-color: {bg_surface} !important;
        border: 1px solid {border_subtle} !important;
        border-radius: 10px !important;
        margin-bottom: 10px !important;
    }}
    [data-testid="stExpander"] summary p {{
        color: {text_primary} !important;
        font-weight: 600 !important;
        font-size: 14px !important;
    }}

    /* Metric Cards */
    div[data-testid="stMetric"] {{
        background: {bg_surface} !important;
        border: 1px solid {border_subtle} !important;
        border-radius: 12px !important;
        padding: 16px 20px !important;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05) !important;
    }}
    div[data-testid="stMetricLabel"] p {{
        font-size: 11px !important;
        font-weight: 600 !important;
        color: {text_secondary} !important;
        text-transform: uppercase !important;
        letter-spacing: 0.05em !important;
    }}
    div[data-testid="stMetricValue"] div {{
        font-size: 26px !important;
        font-weight: 700 !important;
        color: {text_primary} !important;
        letter-spacing: -0.03em !important;
    }}

    /* Decision Cards */
    .rec-card-approve {{
        background: {rec_approve_bg};
        border: 1px solid {rec_approve_border};
        border-left: 4px solid #10B981;
        border-radius: 12px;
        padding: 20px 24px;
        margin-bottom: 20px;
    }}
    .rec-card-changes {{
        background: {rec_changes_bg};
        border: 1px solid {rec_changes_border};
        border-left: 4px solid #EF4444;
        border-radius: 12px;
        padding: 20px 24px;
        margin-bottom: 20px;
    }}
    .rec-badge-approve {{
        display: inline-flex;
        align-items: center;
        gap: 6px;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        color: {rec_approve_text};
        background: {rec_approve_badge};
        border: 1px solid {rec_approve_border};
        padding: 3px 10px;
        border-radius: 9999px;
        margin-bottom: 10px;
    }}
    .rec-badge-changes {{
        display: inline-flex;
        align-items: center;
        gap: 6px;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        color: {rec_changes_text};
        background: {rec_changes_badge};
        border: 1px solid {rec_changes_border};
        padding: 3px 10px;
        border-radius: 9999px;
        margin-bottom: 10px;
    }}
    .rec-title {{
        font-size: 19px;
        font-weight: 700;
        letter-spacing: -0.02em;
        color: {text_primary};
        margin-bottom: 6px;
    }}
    .rec-reason {{
        font-size: 14px;
        color: {text_secondary};
        line-height: 1.5;
    }}

    /* Badges */
    .badge-critical {{
        background: {badge_crit_bg};
        color: {badge_crit_text};
        border: 1px solid {badge_crit_border};
        padding: 2px 7px;
        border-radius: 5px;
        font-size: 11px;
        font-weight: 700;
    }}
    .badge-high {{
        background: {badge_high_bg};
        color: {badge_high_text};
        border: 1px solid {badge_high_border};
        padding: 2px 7px;
        border-radius: 5px;
        font-size: 11px;
        font-weight: 700;
    }}
    .badge-medium {{
        background: {badge_med_bg};
        color: {badge_med_text};
        border: 1px solid {badge_med_border};
        padding: 2px 7px;
        border-radius: 5px;
        font-size: 11px;
        font-weight: 700;
    }}
    .badge-low {{
        background: {badge_low_bg};
        color: {badge_low_text};
        border: 1px solid {badge_low_border};
        padding: 2px 7px;
        border-radius: 5px;
        font-size: 11px;
        font-weight: 700;
    }}

    /* Primary Button */
    button[kind="primary"] {{
        background-color: {btn_bg} !important;
        color: {btn_text} !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 10px 20px !important;
        font-weight: 600 !important;
        font-size: 14px !important;
    }}

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 8px !important;
        border-bottom: 1px solid {border_subtle} !important;
    }}
    .stTabs [data-baseweb="tab"] {{
        font-size: 13px !important;
        font-weight: 600 !important;
        color: {text_secondary} !important;
        padding: 10px 16px !important;
    }}
    .stTabs [aria-selected="true"] {{
        color: {text_primary} !important;
        border-bottom: 2px solid {border_focus} !important;
    }}

    /* Code Blocks */
    .stCodeBlock {{
        border-radius: 8px !important;
        border: 1px solid {border_subtle} !important;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# Top Navigation Bar with Dynamic Theme Indicator
theme_symbol = "☾ Dark Mode" if is_dark else "☀ Light Mode"
st.markdown(
    f"""
    <div class="tva-navbar">
        <div class="tva-brand">
            <span style="color:#0EA5E9; font-size:12px;">●</span>
            <span>ACRB</span>
            <span class="tva-brand-tag">Automated Code Review Board</span>
        </div>
        <div class="tva-nav-links">
            <span class="active">Review Intake</span>
            <span>Analysis</span>
            <span>Remediation</span>
            <span>Artifacts</span>
            <span style="color:{text_secondary}; font-size:12px;">{theme_symbol}</span>
            <div class="tva-status-pill">
                <span class="tva-status-dot"></span>
                <span>Review engine operational</span>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Main Title & Subtitle with Crisp Terminology
st.markdown(
    """
    <div class="intake-header">
        <div class="intake-title">Code Review Intake</div>
        <div class="intake-subtitle">
            Initialize an automated multi-agent code inspection. Upload a unified <span class="code-pill">.diff</span> or <span class="code-pill">.patch</span> file, or select a pre-configured scenario. The deterministic review engine runs strictly offline with machine-verified patch remediation.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Sidebar Configuration
st.sidebar.markdown("### Settings")

view_mode = st.sidebar.radio(
    "Perspective",
    options=["Executive Summary View", "Technical Developer View"],
    index=0,
    help="Toggle between executive health breakdown and technical developer diffs.",
)

execution_mode = st.sidebar.selectbox(
    "Execution Mode",
    options=["offline", "llm"],
    index=1,
    help="Offline runs deterministic rules (<5ms). LLM mode enables model-augmented fix suggestions.",
)

st.sidebar.markdown("---")
st.sidebar.markdown("### Pipeline Architecture")
with st.sidebar.expander("Specialist Review Agents", expanded=False):
    st.markdown("""
        - **Diff Inspector:** Structural metrics, change categorization, and domain risk scanning.
        - **Style Guardian:** Code maintainability, formatting, and complexity compliance.
        - **Security Shield:** Credentials detection and vulnerability analysis.
        - **Test Coverage:** Public symbol interface coverage analysis.
        - **Reviewer Manager:** Aggregation, corroboration, deduplication, and merge recommendation.
        - **Fix-Suggestion Agent:** Machine-verified code patch generation.
        """)

# Sample Files Map
SAMPLE_EXPLANATIONS = {
    "01_clean_change.diff": "Production-Ready Feature (Clean baseline)",
    "02_sql_injection_and_secret.diff": "Security Critical (Credentials & SQL injection)",
    "03_untested_feature.diff": "Coverage Deficit (Untested public functions)",
    "04_style_mess.diff": "Quality Debt (Syntax, complexity & style errors)",
    "05_mixed_realistic.diff": "Real-World Multi-File PR (Compound defects)",
}

samples_dir = ROOT_DIR / "samples" / "diffs"
sample_files = sorted(samples_dir.glob("*.diff")) if samples_dir.exists() else []

# Central Intake Card Matching Reference Design
st.markdown(
    f"""
    <div class="intake-card">
        <div class="intake-card-header">
            <div class="intake-tag">
                <span class="intake-dot"></span>
                <span>Review Input Vector</span>
            </div>
            <div style="font-size:12px; color:{text_secondary};">Unified Diff / Patch Format</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

intake_tab_options = ["Pre-Configured Scenarios", "File Upload (.diff / .patch)", "Raw Text Input"]
chosen_tab = st.radio(
    "Select Input Method",
    options=intake_tab_options,
    horizontal=True,
    label_visibility="collapsed",
)

selected_sample = None
uploaded_file = None
pasted_diff = ""

if chosen_tab == "Pre-Configured Scenarios":
    if sample_files:
        chosen_friendly = st.selectbox(
            "Select Scenario",
            options=[SAMPLE_EXPLANATIONS.get(f.name, f.name) for f in sample_files],
            index=1,
        )
        for f in sample_files:
            if SAMPLE_EXPLANATIONS.get(f.name, f.name) == chosen_friendly:
                selected_sample = f
                break
    else:
        st.warning("No sample diff files found in samples/diffs/")
elif chosen_tab == "File Upload (.diff / .patch)":
    uploaded_file = st.file_uploader(
        "Drop .diff or .patch files here",
        type=["diff", "patch", "txt"],
        help="Upload a standard unified diff file (+ additions, - deletions).",
    )
elif chosen_tab == "Raw Text Input":
    pasted_diff = st.text_area(
        "Paste Unified Diff Here",
        height=180,
        placeholder="diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@ -1,3 +1,4 @@\n+print('hello')",
    )

# Primary Execution Button
btn_col1, btn_col2 = st.columns([1, 3])
with btn_col1:
    run_button = st.button("Execute Review Pipeline", type="primary", use_container_width=True)

# Read selected diff text
raw_diff_text = ""
if selected_sample and selected_sample.exists():
    raw_diff_text = selected_sample.read_text(encoding="utf-8")
elif uploaded_file:
    raw_diff_text = uploaded_file.getvalue().decode("utf-8", errors="replace")
elif pasted_diff:
    raw_diff_text = pasted_diff

if raw_diff_text.strip():
    with st.expander("View Input Unified Diff Buffer", expanded=False):
        st.code(
            raw_diff_text[:3000] + ("\n... [truncated]" if len(raw_diff_text) > 3000 else ""),
            language="diff",
        )


# -----------------------------------------------------------------------------
# 1. EXECUTIVE SUMMARY VIEW
# -----------------------------------------------------------------------------
def render_layman_view(state, review, summary, patch):
    """Render executive overview."""
    is_approved = review.decision == "APPROVE"
    risk_score = review.merge_risk_score
    total_findings = len(review.priority_order)
    crit_count = len(review.findings_by_severity.get(Severity.CRITICAL, []))
    high_count = len(review.findings_by_severity.get(Severity.HIGH, []))
    med_count = len(review.findings_by_severity.get(Severity.MEDIUM, []))
    low_count = len(review.findings_by_severity.get(Severity.LOW, []))

    # Clean Recommendation Card
    if is_approved:
        st.markdown(
            f"""
            <div class="rec-card-approve">
                <div class="rec-badge-approve">● Safe to Merge</div>
                <div class="rec-title">Merge Recommendation: APPROVE</div>
                <div class="rec-reason">
                    The changeset satisfies all defined security, style, and coverage policies. Zero blocking vulnerabilities or critical defects were detected.<br>
                    <strong>Policy Verdict:</strong> {review.decision_reason}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
            <div class="rec-card-changes">
                <div class="rec-badge-changes">● Action Required</div>
                <div class="rec-title">Merge Recommendation: REQUEST CHANGES</div>
                <div class="rec-reason">
                    The review board identified <strong>{crit_count + high_count} blocking issue(s)</strong> exceeding risk tolerance thresholds.<br>
                    <strong>Policy Verdict:</strong> {review.decision_reason}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # 4 Key Scorecards
    col_risk, col_blockers, col_total, col_time = st.columns(4)
    with col_risk:
        st.metric(
            label="Overall Risk Score",
            value=f"{risk_score} / 100",
            delta="Passes Tolerance" if is_approved else "Exceeds Threshold",
            delta_color="normal" if is_approved else "inverse",
        )
    with col_blockers:
        blocker_count = crit_count + high_count
        st.metric(
            label="Must-Fix Blockers",
            value=blocker_count,
            delta=(
                "0 Immediate Blockers"
                if blocker_count == 0
                else f"{blocker_count} Immediate Actions"
            ),
            delta_color="normal" if blocker_count == 0 else "inverse",
        )
    with col_total:
        st.metric(
            label="Total Findings",
            value=total_findings,
            delta=f"{crit_count} Crit • {high_count} High • {med_count} Med • {low_count} Low",
            delta_color="off",
        )
    with col_time:
        total_duration_ms = sum(res.duration_ms for res in state.agent_results.values())
        st.metric(
            label="Pipeline Latency",
            value=f"{total_duration_ms:.1f} ms",
            delta="Sub-second turnaround",
            delta_color="normal",
        )

    st.markdown("<br>", unsafe_allow_html=True)

    tab_simple, tab_problems, tab_autofix, tab_testing, tab_agents, tab_downloads = st.tabs(
        [
            "Executive Summary",
            f"Findings ({total_findings})",
            "Remediation Patch",
            "Test Verification",
            "Specialist Diagnostics",
            "Export Artifacts",
        ]
    )

    # Tab 1: Executive Summary
    with tab_simple:
        st.markdown("#### Health Breakdown")
        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            st.markdown("**Security Posture**")
            if crit_count == 0:
                st.success(
                    "No Credentials or Injections Detected\n\nCode satisfies OWASP standards."
                )
            else:
                st.error(
                    f"{crit_count} Critical Flaw(s) Detected\n\nHard-coded credentials or injection vectors found."
                )
        with sc2:
            st.markdown("**Test Adequacy**")
            if high_count == 0 or not any(
                f.category.value == "test_coverage" for f in review.priority_order
            ):
                st.success("Adequately Tested\n\nNew logic has corresponding test coverage.")
            else:
                st.warning(
                    "Missing Safety Tests\n\nNew public functions introduced without coverage."
                )
        with sc3:
            st.markdown("**Maintainability**")
            if med_count == 0 and low_count == 0:
                st.success("Clean & Compliant\n\nFollows standard naming and style conventions.")
            else:
                st.info(
                    f"{med_count + low_count} Quality Notice(s)\n\nFormatting, docstring, or style items identified."
                )

        st.markdown("---")
        st.markdown("#### Structural Diff Overview")
        if summary:
            st.markdown(f"**Intent Summary:** *{summary.intent_summary}*")
            c_size, c_files, c_lines = st.columns(3)
            c_size.info(f"**Change Size Category:** `{summary.size_class}`")
            c_files.info(f"**Files Touched:** {summary.total_files} file(s)")
            c_lines.info(f"**Lines Changed:** +{summary.lines_added} / -{summary.lines_removed}")
            if summary.risk_areas:
                st.warning(
                    f"Sensitive domains touched: **{', '.join(summary.risk_areas).upper()}**."
                )

    # Tab 2: Findings
    with tab_problems:
        st.markdown("#### Detected Review Findings")
        if not review.priority_order:
            st.success("Zero issues identified in this changeset.")
        else:
            st.caption("Findings ranked in descending priority order:")
            for idx, f in enumerate(review.priority_order, start=1):
                corrob_text = (
                    f" • Corroborated by {len(f.corroborated_by)} agents"
                    if len(f.corroborated_by) > 1
                    else ""
                )
                with st.expander(
                    f"#{idx}. [{f.severity.value}] {f.title} ({f.file_path or 'General'}){corrob_text}"
                ):
                    st.markdown(f"**Description:** {f.description}")
                    if f.code_snippet:
                        st.code(
                            f.code_snippet,
                            language=(
                                "python"
                                if (f.file_path and f.file_path.endswith(".py"))
                                else "text"
                            ),
                        )
                    st.markdown(f"**Recommendation:** {f.recommendation}")
                    st.caption(
                        f"Rule: `{f.rule_id}` | Source: `{f.evidence_source or 'Rule Engine'}`"
                    )

    # Tab 3: Remediation Patch
    with tab_autofix:
        st.markdown("#### Machine-Verified Remediation")
        settings = get_settings()

        if patch:
            verif = patch.verification
            if verif and verif.verdict == "VERIFIED":
                st.success("Patch Verification: VERIFIED (Safe to apply)")
            elif verif and verif.verdict == "PARTIAL":
                st.warning("Patch Verification: PARTIAL")
            else:
                st.error("Patch Verification: REJECTED")

            st.markdown(f"**Target Finding:** `{patch.finding_id}` (`{patch.file_path}`)")
            st.info(f"**Remediation Explanation:** {patch.explanation}")
            st.code(patch.unified_diff, language="diff")

            if verif:
                v1, v2, v3, v4 = st.columns(4)
                v1.metric("Applies Cleanly", "Yes" if verif.applies_cleanly else "No")
                v2.metric("Syntax Valid", "Valid" if verif.syntax_ok else "Broken")
                v3.metric(
                    "Original Flaw Gone",
                    "Resolved" if verif.original_finding_resolved else "Present",
                )
                v4.metric("New Bugs Added", f"{len(verif.new_findings_introduced)}")

            if patch.followups:
                st.markdown("**Follow-Up Actions:**")
                for act in patch.followups:
                    st.markdown(f"- {act}")

        # Per-finding fix suggestions (LLM mode)
        suggestions = getattr(state, "fix_suggestions", [])
        if suggestions:
            st.markdown("---")
            st.markdown(f"#### Additional Fix Suggestions ({len(suggestions)})")
            for idx, sug in enumerate(suggestions, start=1):
                badge_text = (
                    "● VERIFIED"
                    if (sug.verification and sug.verification.verdict == "VERIFIED")
                    else ("Manual Guidance" if sug.kind == "manual" else "Syntax Checked")
                )
                with st.expander(
                    f"Suggestion #{idx}: {sug.rule_id} ({sug.file_path or 'file'}) — {badge_text}"
                ):
                    st.write(f"**Explanation:** {sug.explanation}")
                    if sug.unified_diff:
                        st.code(sug.unified_diff, language="diff")
                    if sug.note:
                        st.caption(f"Note: {sug.note}")
        elif not patch:
            if settings.effective_mode == "offline":
                st.info(
                    "Automated fix suggestions are enabled in LLM mode (--mode llm with API key). "
                    "In offline mode, deterministic analysis is performed."
                )
            else:
                st.info(
                    "No automated remediation patch required or synthesized for this changeset."
                )

    # Tab 4: Test Verification
    with tab_testing:
        st.markdown("#### Test Adequacy & Coverage")
        try:
            from plugins.coverage_plugin import CoveragePlugin

            cov = CoveragePlugin().analyze_coverage(state.files)
            st.markdown(
                f"**Change Test Ratio:** `{cov.get('test_ratio', 0.0):.2f}` (test lines added / source lines added)"
            )
            symbol_map = cov.get("symbol_map", [])
            if symbol_map:
                st.table(symbol_map)
            else:
                st.info("No new public functions or classes declared in this changeset.")
        except Exception as exc:
            st.warning(f"Could not compute coverage table: {exc}")

    # Tab 5: Specialist Diagnostics
    with tab_agents:
        st.markdown("#### Specialist Concurrency & Diagnostics")
        agent_cards = [
            (
                "Diff Inspector",
                "Change Metrics & Domain Risk",
                state.agent_results.get("diff_agent"),
            ),
            (
                "Style Guardian",
                "Maintainability & Standards",
                state.agent_results.get("style_agent"),
            ),
            (
                "Security Shield",
                "Credentials & Vulnerabilities",
                state.agent_results.get("security_agent"),
            ),
            (
                "Test Coverage",
                "Interface Coverage Verification",
                state.agent_results.get("test_coverage_agent"),
            ),
            (
                "Reviewer Manager",
                "Aggregation & Policy Verdict",
                state.agent_results.get("reviewer_manager"),
            ),
        ]
        a_cols = st.columns(len(agent_cards))
        for i, (name, role, res) in enumerate(agent_cards):
            with a_cols[i]:
                st.markdown(f"**{name}**")
                st.caption(role)
                if res:
                    st.markdown(f"**Status:** {'OK' if res.status == 'ok' else 'Failed'}")
                    st.markdown(f"**Time:** `{res.duration_ms:.1f}ms`")
                    st.markdown(f"**Findings:** `{len(res.findings)}`")
                else:
                    st.caption("Standby")

        st.markdown("---")
        st.markdown("#### Execution Timeline")
        timeline_rows = [
            {
                "Agent": t.agent_name,
                "Event": t.event.upper(),
                "Timestamp": t.timestamp,
                "Duration": f"{t.duration_ms:.1f} ms" if t.duration_ms is not None else "-",
            }
            for t in state.timeline
        ]
        st.dataframe(timeline_rows, use_container_width=True)

    # Tab 6: Downloads
    with tab_downloads:
        st.markdown("#### Export Artifacts")
        settings = get_settings()
        md_content = generate_markdown_report(state, mode=settings.effective_mode)
        json_content = generate_json_report(state)
        d1, d2 = st.columns(2)
        with d1:
            st.download_button(
                label="Download Markdown Report (review.md)",
                data=md_content,
                file_name=f"review_{state.change_id}.md",
                mime="text/markdown",
                use_container_width=True,
            )
        with d2:
            st.download_button(
                label="Download Raw JSON Data (review.json)",
                data=json_content,
                file_name=f"review_{state.change_id}.json",
                mime="application/json",
                use_container_width=True,
            )


# -----------------------------------------------------------------------------
# 2. TECHNICAL DEVELOPER VIEW
# -----------------------------------------------------------------------------
def render_technical_view(state, review, summary, patch):
    """Render technical developer view."""
    col_rec, col_score, col_findings = st.columns([2, 1, 1])
    with col_rec:
        if review.decision == "APPROVE":
            st.markdown(
                """
                <div class="rec-card-approve">
                    <div class="rec-badge-approve">● APPROVE</div>
                    <div class="rec-title">Merge Recommendation: APPROVE</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                """
                <div class="rec-card-changes">
                    <div class="rec-badge-changes">● REQUEST CHANGES</div>
                    <div class="rec-title">Merge Recommendation: REQUEST CHANGES</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        st.write(f"**Policy Reason:** {review.decision_reason}")

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
            label="Deduplicated Findings",
            value=total_f,
            delta=f"{crit_f} Critical",
            delta_color="inverse" if crit_f > 0 else "off",
        )

    st.divider()

    tab_findings, tab_patch, tab_coverage, tab_summary, tab_timeline, tab_export = st.tabs(
        [
            f"Findings ({total_f})",
            "Remediation Patch",
            "Coverage Map",
            "Change Summary",
            "Agent Timeline",
            "Export Reports",
        ]
    )

    # Technical Tab 1: Findings by Severity
    with tab_findings:
        st.markdown("#### Prioritized Review Findings")
        if not review.priority_order:
            st.info("Zero findings detected. Changeset meets all acceptance standards.")
        else:
            for f in review.priority_order:
                corrob_str = (
                    f" • Corroborated by {len(f.corroborated_by)} agents"
                    if len(f.corroborated_by) > 1
                    else ""
                )
                with st.expander(
                    f"Rank #{f.priority_rank} [{f.severity.value}] {f.title} ({f.file_path or 'global'}){corrob_str}"
                ):
                    st.write(f"**Explanation:** {f.description}")
                    if f.code_snippet:
                        st.code(f.code_snippet, language="python")
                    st.write(f"**Recommendation:** {f.recommendation}")
                    st.caption(
                        f"Rule: `{f.rule_id}` | Evidence: `{f.evidence_source or 'Ungrounded'}` | Confidence: {int(f.confidence * 100)}%"
                    )

    # Technical Tab 2: Suggested Verified Patch
    with tab_patch:
        st.markdown("#### Machine-Verified Remediation Patch")
        settings = get_settings()
        if patch:
            verif = patch.verification
            if verif:
                if verif.verdict == "VERIFIED":
                    st.success("Patch Verification: VERIFIED (Safe to Merge)")
                elif verif.verdict == "PARTIAL":
                    st.warning("Patch Verification: PARTIAL (Quality Notices)")
                else:
                    st.error("Patch Verification: REJECTED (Unsafe or Context Mismatch)")

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

        # Per-finding fix suggestions (LLM mode)
        suggestions = getattr(state, "fix_suggestions", [])
        if suggestions:
            st.markdown("---")
            st.markdown(f"#### Fix Suggestions ({len(suggestions)})")
            for idx, sug in enumerate(suggestions, start=1):
                badge = (
                    "VERIFIED"
                    if (sug.verification and sug.verification.verdict == "VERIFIED")
                    else (
                        "PARTIAL"
                        if (sug.verification and sug.verification.verdict == "PARTIAL")
                        else (
                            "REJECTED"
                            if (sug.verification and sug.verification.verdict == "REJECTED")
                            else ("syntax-checked" if sug.kind == "new_file" else "manual guidance")
                        )
                    )
                )
                loc = (
                    f"{sug.file_path}:{sug.line_start}"
                    if sug.line_start
                    else (sug.file_path or "-")
                )
                with st.expander(
                    f"Fix #{idx}: `{sug.rule_id}` [{sug.severity.value}] ({loc}) — {badge}"
                ):
                    st.write(f"**Kind:** `{sug.kind}` | **Source:** `{sug.source}`")
                    st.write(f"**Explanation:** {sug.explanation}")
                    if sug.unified_diff:
                        st.code(sug.unified_diff, language="diff")
                    if sug.new_imports:
                        st.write(f"**New Imports:** {', '.join(f'`{i}`' for i in sug.new_imports)}")
                    if sug.followups:
                        st.write("**Follow-up Actions:**")
                        for act in sug.followups:
                            st.write(f"- {act}")
                    if sug.note:
                        st.caption(f"Note: {sug.note}")
        elif not patch:
            if settings.effective_mode == "offline":
                st.info(
                    "Fix suggestions are available in LLM mode (--mode llm with API key configured). "
                    "In offline mode, automated fixes are disabled."
                )
            else:
                st.info(
                    "No automated remediation patch required or synthesized for this changeset."
                )

    # Technical Tab 3: Test Coverage
    with tab_coverage:
        st.markdown("#### Test Adequacy & Symbol Coverage")
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
        st.markdown("#### Diff Analysis & Risk Areas")
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
        st.markdown("#### Specialist Concurrency Timeline")
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
        st.markdown("#### Download Generated Artifacts")
        settings = get_settings()
        md_content = generate_markdown_report(state, mode=settings.effective_mode)
        json_content = generate_json_report(state)

        c_md, c_json = st.columns(2)
        with c_md:
            st.download_button(
                label="Download review.md",
                data=md_content,
                file_name=f"review_{state.change_id}.md",
                mime="text/markdown",
                use_container_width=True,
            )
        with c_json:
            st.download_button(
                label="Download review.json",
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
        with st.spinner("Executing specialist pipeline (Diff, Style, Security, Coverage)..."):
            state = load_diff_from_stdin(raw_diff_text)
            orchestrator = ReviewOrchestrator(settings=settings)
            state = asyncio.run(orchestrator.run_review(state))

        st.session_state["review_state"] = state
        st.session_state["last_diff_text"] = raw_diff_text
    except Exception as exc:
        st.error(
            f"Failed to parse or review diff: {exc}\n\n"
            "Please ensure the input is in valid Unified Diff format."
        )

# Render active review if available in session state
if "review_state" in st.session_state and st.session_state["review_state"]:
    cached_state = st.session_state["review_state"]
    review = cached_state.consolidated_review
    summary = cached_state.summary
    patch = cached_state.suggested_patch or (review.suggested_patch if review else None)

    # Check if user changed the input without re-running review
    if (
        raw_diff_text.strip()
        and raw_diff_text.strip() != st.session_state.get("last_diff_text", "").strip()
    ):
        st.warning(
            "Input buffer modified: Select Execute Review Pipeline to analyze the updated document."
        )

    if review:
        st.markdown("---")
        if "Technical" in view_mode:
            render_technical_view(cached_state, review, summary, patch)
        else:
            render_layman_view(cached_state, review, summary, patch)
