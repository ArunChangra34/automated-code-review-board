"""Vercel Serverless Function entrypoint and ASGI Web Application for the Automated Code Review Board."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from starlette.applications import Starlette  # noqa: E402
from starlette.requests import Request  # noqa: E402
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse  # noqa: E402
from starlette.routing import Route  # noqa: E402

from config.settings import get_settings  # noqa: E402
from core.diff_loader import load_diff_from_stdin  # noqa: E402
from core.orchestrator import ReviewOrchestrator  # noqa: E402
from reporting.json_report import generate_json_report  # noqa: E402
from reporting.markdown_report import generate_markdown_report  # noqa: E402

SAMPLE_DIFFS = {
    "01_clean_change.diff": "Production-Ready Feature (Clean baseline)",
    "02_sql_injection_and_secret.diff": "Security Critical (Credentials & SQL injection)",
    "03_untested_feature.diff": "Coverage Deficit (Untested public functions)",
    "04_style_mess.diff": "Quality Debt (Syntax, complexity & style errors)",
    "05_mixed_realistic.diff": "Real-World Multi-File PR (Compound defects)",
}


async def health(request: Request) -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse(
        {"status": "ok", "service": "Automated Code Review Board", "runtime": "vercel-python"}
    )


async def list_scenarios(request: Request) -> JSONResponse:
    """Return available pre-configured scenarios."""
    scenarios = []
    samples_dir = ROOT_DIR / "samples" / "diffs"
    for filename, label in SAMPLE_DIFFS.items():
        file_path = samples_dir / filename
        exists = file_path.exists()
        scenarios.append(
            {
                "filename": filename,
                "label": label,
                "available": exists,
            }
        )
    return JSONResponse({"scenarios": scenarios})


async def get_sample(request: Request) -> PlainTextResponse | JSONResponse:
    """Return sample diff file content."""
    filename = request.path_params.get("filename", "")
    if filename not in SAMPLE_DIFFS:
        return JSONResponse({"error": "Scenario not found"}, status_code=404)
    file_path = ROOT_DIR / "samples" / "diffs" / filename
    if not file_path.exists():
        return JSONResponse({"error": "File does not exist"}, status_code=404)
    return PlainTextResponse(file_path.read_text(encoding="utf-8"))


def _str_val(v: any) -> str:
    if v is None:
        return ""
    return str(v.value) if hasattr(v, "value") else str(v)


async def run_review_api(request: Request) -> JSONResponse:
    """Execute review pipeline on provided diff text."""
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    raw_diff = data.get("diff", "")
    mode = data.get("mode", "offline")

    if not raw_diff or not raw_diff.strip():
        return JSONResponse({"error": "Diff content cannot be empty"}, status_code=400)

    try:
        settings = get_settings()
        settings.mode = mode

        state = load_diff_from_stdin(raw_diff)
        orchestrator = ReviewOrchestrator(settings=settings)
        state = await orchestrator.run_review(state)

        review = state.consolidated_review
        findings_source = (
            review.priority_order if review and review.priority_order else state.all_findings
        )
        findings = [
            {
                "id": f.id,
                "rule_id": f.rule_id,
                "severity": _str_val(f.severity),
                "category": _str_val(f.category),
                "title": f.title,
                "description": f.description,
                "file_path": f.file_path,
                "line_start": f.line_start,
                "line_end": f.line_end,
                "recommendation": f.recommendation,
                "code_snippet": f.code_snippet,
            }
            for f in findings_source
        ]

        fix_suggestions_raw = getattr(state, "fix_suggestions", [])
        fixes = [
            {
                "id": fx.id,
                "finding_id": fx.finding_id,
                "rule_id": fx.rule_id,
                "status": _str_val(fx.status),
                "explanation": fx.explanation,
                "patch_content": fx.patch_content,
                "target_file": fx.target_file,
            }
            for fx in fix_suggestions_raw
        ]

        md_report = generate_markdown_report(state, mode=settings.effective_mode)
        json_report = generate_json_report(state)

        stats_dict = {}
        if review and review.stats:
            stats_dict = (
                review.stats.model_dump()
                if hasattr(review.stats, "model_dump")
                else dict(review.stats)
            )

        return JSONResponse(
            {
                "status": "success",
                "change_id": state.change_id,
                "decision": _str_val(review.decision) if review else "REQUEST_CHANGES",
                "decision_reason": review.decision_reason if review else "Review incomplete",
                "merge_risk_score": review.merge_risk_score if review else 0.0,
                "stats": stats_dict,
                "findings": findings,
                "fix_suggestions": fixes,
                "reports": {
                    "markdown": md_report,
                    "json": json_report,
                },
            }
        )
    except Exception as exc:
        return JSONResponse({"error": f"Failed to execute review: {str(exc)}"}, status_code=500)


HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Automated Code Review Board</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-app: #0B0F19;
      --bg-surface: #111827;
      --border-subtle: #1F293D;
      --border-focus: #38BDF8;
      --text-primary: #F8FAFC;
      --text-secondary: #94A3B8;
      --tag-bg: #1E293B;
      --btn-bg: #38BDF8;
      --btn-text: #0B0F19;
      --font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    [data-theme="light"] {
      --bg-app: #FAFAFA;
      --bg-surface: #FFFFFF;
      --border-subtle: #E2E8F0;
      --border-focus: #0F172A;
      --text-primary: #0F172A;
      --text-secondary: #64748B;
      --tag-bg: #F1F5F9;
      --btn-bg: #0F172A;
      --btn-text: #FFFFFF;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg-app);
      color: var(--text-primary);
      font-family: var(--font-family);
      line-height: 1.5;
      padding: 24px;
      transition: background-color 0.2s ease, color 0.2s ease;
    }
    .container {
      max-width: 1140px;
      margin: 0 auto;
    }
    /* Top Navbar */
    .navbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 12px 24px;
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      margin-bottom: 2rem;
      box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 8px;
      font-weight: 700;
      font-size: 14px;
      letter-spacing: -0.02em;
    }
    .brand-dot { width: 8px; height: 8px; border-radius: 50%; background: #0EA5E9; }
    .brand-tag { font-weight: 400; color: var(--text-secondary); font-size: 13px; margin-left: 2px; }
    .nav-links {
      display: flex;
      align-items: center;
      gap: 20px;
      font-size: 13px;
      font-weight: 500;
      color: var(--text-secondary);
    }
    .nav-links span.active { color: var(--text-primary); font-weight: 600; }
    .theme-toggle {
      background: var(--tag-bg);
      border: 1px solid var(--border-subtle);
      color: var(--text-primary);
      padding: 4px 10px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 12px;
      font-weight: 600;
    }
    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      border-radius: 9999px;
      background: var(--tag-bg);
      font-size: 12px;
      font-weight: 500;
    }
    .status-dot { width: 7px; height: 7px; border-radius: 50%; background: #10B981; }

    /* Header */
    .intake-header { margin-bottom: 24px; }
    .intake-title { font-size: 30px; font-weight: 700; letter-spacing: -0.03em; margin-bottom: 6px; }
    .intake-subtitle { font-size: 14px; color: var(--text-secondary); line-height: 1.6; max-width: 800px; }
    .code-pill {
      background: var(--tag-bg);
      border: 1px solid var(--border-subtle);
      padding: 2px 6px;
      border-radius: 4px;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 12px;
    }

    /* Central Card */
    .intake-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 16px;
      box-shadow: 0 10px 30px -5px rgba(0, 0, 0, 0.08);
      padding: 24px 28px;
      margin-bottom: 24px;
    }
    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid var(--border-subtle);
      padding-bottom: 14px;
      margin-bottom: 20px;
    }
    .tag {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--text-secondary);
    }
    .tab-group {
      display: flex;
      gap: 12px;
      margin-bottom: 20px;
    }
    .tab-btn {
      background: transparent;
      border: 1px solid var(--border-subtle);
      color: var(--text-secondary);
      padding: 8px 16px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .tab-btn.active {
      background: var(--tag-bg);
      border-color: var(--border-focus);
      color: var(--text-primary);
    }
    .tab-pane { display: none; }
    .tab-pane.active { display: block; }

    /* Dropzone */
    .dropzone {
      border: 2px dashed var(--border-subtle);
      border-radius: 12px;
      padding: 40px 20px;
      text-align: center;
      cursor: pointer;
      transition: border-color 0.2s;
    }
    .dropzone:hover { border-color: var(--border-focus); }
    .dropzone-icon {
      margin-bottom: 12px;
      color: var(--text-secondary);
    }

    /* Inputs */
    select, textarea {
      width: 100%;
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      color: var(--text-primary);
      padding: 10px 14px;
      border-radius: 8px;
      font-size: 14px;
      font-family: inherit;
      outline: none;
    }
    select:focus, textarea:focus { border-color: var(--border-focus); }
    textarea {
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 13px;
      min-height: 180px;
      resize: vertical;
    }

    /* Primary Action */
    .btn-primary {
      background: var(--btn-bg);
      color: var(--btn-text);
      border: none;
      border-radius: 8px;
      padding: 12px 24px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      margin-top: 20px;
      transition: opacity 0.15s ease;
    }
    .btn-primary:hover { opacity: 0.9; }
    .btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

    /* Decision Cards */
    .decision-card {
      border-radius: 12px;
      padding: 22px 26px;
      margin-bottom: 24px;
      border-left: 5px solid;
    }
    .decision-approve {
      background: rgba(16, 185, 129, 0.08);
      border: 1px solid #059669;
      border-left: 5px solid #10B981;
    }
    .decision-changes {
      background: rgba(239, 68, 68, 0.08);
      border: 1px solid #DC2626;
      border-left: 5px solid #EF4444;
    }
    .badge {
      display: inline-block;
      padding: 3px 10px;
      border-radius: 9999px;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 10px;
    }
    .badge-approve { background: #064E3B; color: #34D399; }
    .badge-changes { background: #7F1D1D; color: #F87171; }

    /* Metrics Grid */
    .metrics-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }
    .metric-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      padding: 16px 20px;
    }
    .metric-title {
      font-size: 11px;
      font-weight: 600;
      color: var(--text-secondary);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 6px;
    }
    .metric-val {
      font-size: 26px;
      font-weight: 700;
      letter-spacing: -0.03em;
    }

    /* Findings List */
    .finding-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 10px;
      padding: 16px 20px;
      margin-bottom: 12px;
    }
    .finding-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
    }
    .finding-title { font-size: 15px; font-weight: 600; }
    .finding-desc { font-size: 13px; color: var(--text-secondary); margin-bottom: 10px; line-height: 1.5; }
    .sev-pill {
      font-size: 11px;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 4px;
      text-transform: uppercase;
    }
    .sev-CRITICAL { background: #450A0A; color: #FCA5A5; border: 1px solid #7F1D1D; }
    .sev-HIGH { background: #451A03; color: #FCD34D; border: 1px solid #78350F; }
    .sev-MEDIUM { background: #422006; color: #FDE047; border: 1px solid #713F12; }
    .sev-LOW { background: #172554; color: #93C5FD; border: 1px solid #1E3A8A; }

    pre {
      background: var(--tag-bg);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 12px;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 12px;
      overflow-x: auto;
      margin-top: 8px;
    }
  </style>
</head>
<body>
  <div class="container">
    <!-- Navbar -->
    <div class="navbar">
      <div class="brand">
        <span class="brand-dot"></span>
        <span>ACRB</span>
        <span class="brand-tag">Automated Code Review Board</span>
      </div>
      <div class="nav-links">
        <span class="active">Review Intake</span>
        <span>Specialist Analysis</span>
        <span>Remediation</span>
        <span>Artifacts</span>
        <button class="theme-toggle" id="themeBtn" onclick="toggleTheme()">☾ Dark</button>
        <div class="status-pill">
          <span class="status-dot"></span>
          <span>Review engine operational</span>
        </div>
      </div>
    </div>

    <!-- Header -->
    <div class="intake-header">
      <div class="intake-title">Code Review Intake</div>
      <div class="intake-subtitle">
        Initialize an automated multi-agent code inspection. Upload a unified <span class="code-pill">.diff</span> or <span class="code-pill">.patch</span> file, or select a pre-configured scenario. The deterministic review engine runs strictly offline with machine-verified patch remediation.
      </div>
    </div>

    <!-- Intake Card -->
    <div class="intake-card">
      <div class="card-header">
        <div class="tag">
          <span class="brand-dot" style="width:6px; height:6px;"></span>
          <span>Review Input Vector</span>
        </div>
        <div style="font-size:12px; color:var(--text-secondary);">Unified Diff / Patch Format</div>
      </div>

      <!-- Input Tabs -->
      <div class="tab-group">
        <button class="tab-btn active" onclick="switchTab(0)">Pre-Configured Scenarios</button>
        <button class="tab-btn" onclick="switchTab(1)">File Upload (.diff / .patch)</button>
        <button class="tab-btn" onclick="switchTab(2)">Raw Text Input</button>
      </div>

      <!-- Tab 0: Scenario -->
      <div class="tab-pane active" id="pane0">
        <label style="font-size:12px; font-weight:600; color:var(--text-secondary); display:block; margin-bottom:6px;">Select Scenario</label>
        <select id="scenarioSelect" onchange="loadSelectedScenario()">
          <option value="01_clean_change.diff">Production-Ready Feature (Clean baseline)</option>
          <option value="02_sql_injection_and_secret.diff" selected>Security Critical (Credentials & SQL injection)</option>
          <option value="03_untested_feature.diff">Coverage Deficit (Untested public functions)</option>
          <option value="04_style_mess.diff">Quality Debt (Syntax, complexity & style errors)</option>
          <option value="05_mixed_realistic.diff">Real-World Multi-File PR (Compound defects)</option>
        </select>
      </div>

      <!-- Tab 1: File Upload -->
      <div class="tab-pane" id="pane1">
        <div class="dropzone" onclick="document.getElementById('fileInput').click()">
          <div class="dropzone-icon">
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
          </div>
          <div style="font-weight:600; font-size:14px; margin-bottom:4px;">Drop .diff or .patch files here</div>
          <div style="font-size:12px; color:var(--text-secondary);">or click to browse from your device</div>
          <input type="file" id="fileInput" style="display:none" accept=".diff,.patch,.txt" onchange="handleFileUpload(event)">
        </div>
      </div>

      <!-- Tab 2: Raw Input -->
      <div class="tab-pane" id="pane2">
        <textarea id="rawInput" placeholder="Paste unified diff content here (starts with diff --git or --- a/ ...)" oninput="syncDiffText()"></textarea>
      </div>

      <!-- Execution Mode and Action -->
      <div style="display:flex; justify-content:space-between; align-items:flex-end; margin-top:20px; flex-wrap:wrap; gap:16px;">
        <div style="width:220px;">
          <label style="font-size:12px; font-weight:600; color:var(--text-secondary); display:block; margin-bottom:6px;">Execution Mode</label>
          <select id="modeSelect">
            <option value="offline" selected>Offline (Deterministic &lt;5ms)</option>
            <option value="llm">LLM (Automated Patch Fixes)</option>
          </select>
        </div>
        <button class="btn-primary" id="runBtn" onclick="executeReview()">
          <span>Execute Review Pipeline</span>
        </button>
      </div>
    </div>

    <!-- Results Section -->
    <div id="results" style="display:none;"></div>
  </div>

  <script>
    let activeDiff = '';
    let currentTheme = localStorage.getItem('acrb_theme') || 'dark';

    function initTheme() {
      document.documentElement.setAttribute('data-theme', currentTheme);
      document.getElementById('themeBtn').innerText = currentTheme === 'dark' ? '☾ Dark' : '☀ Light';
    }
    function toggleTheme() {
      currentTheme = currentTheme === 'dark' ? 'light' : 'dark';
      localStorage.setItem('acrb_theme', currentTheme);
      initTheme();
    }
    initTheme();

    function switchTab(index) {
      document.querySelectorAll('.tab-btn').forEach((b, i) => b.classList.toggle('active', i === index));
      document.querySelectorAll('.tab-pane').forEach((p, i) => p.classList.toggle('active', i === index));
      if (index === 0) loadSelectedScenario();
    }

    async function loadSelectedScenario() {
      const filename = document.getElementById('scenarioSelect').value;
      try {
        const res = await fetch(`/api/sample/${filename}`);
        if (res.ok) {
          activeDiff = await res.text();
          document.getElementById('rawInput').value = activeDiff;
        }
      } catch (err) {
        console.error('Failed to load sample:', err);
      }
    }
    loadSelectedScenario();

    function handleFileUpload(e) {
      const file = e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (event) => {
        activeDiff = event.target.result;
        document.getElementById('rawInput').value = activeDiff;
        alert(`Loaded file: ${file.name} (${activeDiff.length} bytes)`);
      };
      reader.readAsText(file);
    }

    function syncDiffText() {
      activeDiff = document.getElementById('rawInput').value;
    }

    async function executeReview() {
      syncDiffText();
      if (!activeDiff || !activeDiff.trim()) {
        alert('Please select a scenario, upload a diff file, or paste diff text.');
        return;
      }
      const btn = document.getElementById('runBtn');
      btn.disabled = true;
      btn.innerText = 'Analyzing Pipeline...';

      const mode = document.getElementById('modeSelect').value;

      try {
        const res = await fetch('/api/review', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ diff: activeDiff, mode: mode })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Review request failed');
        renderResults(data);
      } catch (err) {
        alert('Error: ' + err.message);
      } finally {
        btn.disabled = false;
        btn.innerText = 'Execute Review Pipeline';
      }
    }

    function renderResults(data) {
      const resultsDiv = document.getElementById('results');
      resultsDiv.style.display = 'block';

      const isApprove = data.decision === 'APPROVE';
      const decClass = isApprove ? 'decision-approve' : 'decision-changes';
      const badgeClass = isApprove ? 'badge-approve' : 'badge-changes';
      const decTitle = isApprove ? 'Approved for Merge' : 'Changes Requested';

      const stats = data.stats || {};
      const crit = stats.critical_findings || 0;
      const high = stats.high_findings || 0;
      const med = (stats.medium_findings || 0) + (stats.low_findings || 0);
      const score = (data.merge_risk_score * 100).toFixed(0);

      let fixesHtml = '';
      if (data.fix_suggestions && data.fix_suggestions.length > 0) {
        fixesHtml = `
          <div class="intake-card" style="margin-top:20px;">
            <div class="card-header">
              <div class="tag"><span>Automated Remediation Patches</span></div>
              <div style="font-size:12px; color:var(--text-secondary);">${data.fix_suggestions.length} verified candidate(s)</div>
            </div>
            ${data.fix_suggestions.map(fx => `
              <div style="margin-bottom:16px;">
                <div style="display:flex; justify-content:space-between; font-weight:600; font-size:13px; margin-bottom:4px;">
                  <span>Rule: ${fx.rule_id}</span>
                  <span class="badge badge-approve">${fx.status}</span>
                </div>
                <div style="font-size:13px; color:var(--text-secondary); margin-bottom:6px;">${fx.explanation}</div>
                <pre><code>${escapeHtml(fx.patch_content || 'Manual verification recommended')}</code></pre>
              </div>
            `).join('')}
          </div>
        `;
      }

      let findingsHtml = '';
      if (data.findings && data.findings.length > 0) {
        findingsHtml = `
          <div class="intake-card" style="margin-top:20px;">
            <div class="card-header">
              <div class="tag"><span>Inspection Findings</span></div>
              <div style="font-size:12px; color:var(--text-secondary);">${data.findings.length} defect(s) detected</div>
            </div>
            ${data.findings.map(f => `
              <div class="finding-card">
                <div class="finding-header">
                  <span class="finding-title">${escapeHtml(f.title)}</span>
                  <span class="sev-pill sev-${f.severity}">${f.severity}</span>
                </div>
                <div class="finding-desc">${escapeHtml(f.description)}</div>
                <div style="font-size:12px; color:var(--text-secondary); margin-bottom:4px;">
                  File: <code class="code-pill">${escapeHtml(f.file_path || 'diff')}</code> Line: ${f.line_start || 1} | Rule: ${escapeHtml(f.rule_id)}
                </div>
                ${f.code_snippet ? `<pre><code>${escapeHtml(f.code_snippet)}</code></pre>` : ''}
              </div>
            `).join('')}
          </div>
        `;
      }

      resultsDiv.innerHTML = `
        <div class="decision-card ${decClass}">
          <span class="badge ${badgeClass}">${data.decision}</span>
          <div style="font-size:22px; font-weight:700; margin-bottom:6px;">${decTitle}</div>
          <div style="font-size:14px; line-height:1.5;">${escapeHtml(data.decision_reason)}</div>
        </div>

        <div class="metrics-grid">
          <div class="metric-card">
            <div class="metric-title">Critical Defects</div>
            <div class="metric-val" style="color:#F87171;">${crit}</div>
          </div>
          <div class="metric-card">
            <div class="metric-title">High Severity</div>
            <div class="metric-val" style="color:#FBBF24;">${high}</div>
          </div>
          <div class="metric-card">
            <div class="metric-title">Medium / Low</div>
            <div class="metric-val" style="color:#60A5FA;">${med}</div>
          </div>
          <div class="metric-card">
            <div class="metric-title">Merge Risk Score</div>
            <div class="metric-val">${score} / 100</div>
          </div>
        </div>

        ${fixesHtml}
        ${findingsHtml}
      `;

      resultsDiv.scrollIntoView({ behavior: 'smooth' });
    }

    function escapeHtml(str) {
      if (!str) return '';
      return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
  </script>
</body>
</html>
"""


async def serve_index(request: Request) -> HTMLResponse:
    """Serve single-page web UI."""
    return HTMLResponse(HTML_CONTENT)


routes = [
    Route("/", endpoint=serve_index, methods=["GET"]),
    Route("/api/health", endpoint=health, methods=["GET"]),
    Route("/api/scenarios", endpoint=list_scenarios, methods=["GET"]),
    Route("/api/sample/{filename}", endpoint=get_sample, methods=["GET"]),
    Route("/api/review", endpoint=run_review_api, methods=["POST"]),
]

app = Starlette(routes=routes)
