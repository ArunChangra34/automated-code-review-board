"""Rich terminal console reporting for Automated Code Review Board."""

from __future__ import annotations

from rich.box import ROUNDED
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from core.models import Severity
from core.state import ChangeState
from plugins.coverage_plugin import CoveragePlugin


def print_console_report(state: ChangeState, console: Console | None = None) -> None:
    """Print an interactive, color-coded console report using Rich."""
    console = console or Console()
    review = state.consolidated_review
    summary = state.summary
    patch = state.suggested_patch or (review.suggested_patch if review else None)

    # 1. Header Banner
    console.print()
    header_text = Text()
    header_text.append("AUTOMATED CODE REVIEW BOARD\n", style="bold white")
    header_text.append(f"Change ID: {state.change_id} | Source: {state.source}", style="dim")
    console.print(
        Panel(header_text, border_style="blue", box=ROUNDED, title="[bold]Code Review[/bold]")
    )

    # 2. Merge Recommendation Banner
    if review:
        if review.decision == "APPROVE":
            border_color = "green"
            rec_icon = "✅ APPROVE"
            rec_style = "bold green"
        else:
            border_color = "red"
            rec_icon = "❌ REQUEST CHANGES"
            rec_style = "bold red"

        rec_content = Text()
        rec_content.append(f"{rec_icon}  ", style=rec_style)
        rec_content.append(f"[Merge-Risk Score: {review.merge_risk_score}/100]\n\n", style="bold")
        rec_content.append(f"Why this decision:\n{review.decision_reason}", style="white")

        console.print(
            Panel(
                rec_content,
                title="[bold]Merge Recommendation[/bold]",
                border_style=border_color,
                box=ROUNDED,
            )
        )
    console.print()

    # 3. Change Summary Table
    if summary:
        sum_table = Table(title="Change Summary", box=ROUNDED, header_style="bold cyan")
        sum_table.add_column("File Path", style="dim")
        sum_table.add_column("Type", justify="center")
        sum_table.add_column("+/-", justify="right")
        sum_table.add_column("Role", justify="center")
        sum_table.add_column("Language", justify="center")

        for f in summary.files:
            sum_table.add_row(
                f.path,
                f.change_type,
                f"+{f.lines_added} / -{f.lines_removed}",
                f.role,
                f.language,
            )

        console.print(sum_table)
        risk_areas = ", ".join(summary.risk_areas) if summary.risk_areas else "None"
        console.print(
            f"Size: [bold]{summary.size_class}[/bold] | "
            f"Total Lines: [green]+{summary.lines_added}[/green] / [red]-{summary.lines_removed}[/red] | "
            f"Risk Areas: [yellow]{risk_areas}[/yellow]"
        )
        console.print()

    # 4. Findings Table
    if review and review.priority_order:
        find_table = Table(title="Review Findings (Priority Order)", box=ROUNDED)
        find_table.add_column("Rank", justify="right", style="bold", width=6)
        find_table.add_column("Severity", justify="center", width=10)
        find_table.add_column("Rule ID", style="cyan", width=14)
        find_table.add_column("Location", style="dim", width=22)
        find_table.add_column("Title & Corroboration")

        sev_colors = {
            Severity.CRITICAL: "bold white on red",
            Severity.HIGH: "bold red",
            Severity.MEDIUM: "bold yellow",
            Severity.LOW: "bold blue",
            Severity.INFO: "dim cyan",
        }

        for finding in review.priority_order:
            sev_style = sev_colors.get(finding.severity, "white")
            loc = (
                f"{finding.file_path}:{finding.line_start}"
                if finding.file_path and finding.line_start
                else (finding.file_path or "global")
            )
            title_text = Text(finding.title)
            if len(finding.corroborated_by) > 1:
                title_text.append(
                    f" [🎯 Corroborated by {len(finding.corroborated_by)} agents]",
                    style="bold green",
                )
            find_table.add_row(
                str(finding.priority_rank or "-"),
                Text(finding.severity.value, style=sev_style),
                finding.rule_id,
                loc,
                title_text,
            )

        console.print(find_table)
        console.print()

    # 5. Test Coverage Map
    try:
        cov_plugin = CoveragePlugin()
        cov_res = cov_plugin.analyze_coverage(state.files)
        symbol_map = cov_res.get("symbol_map", [])
        test_ratio = cov_res.get("test_ratio", 0.0)

        cov_table = Table(
            title=f"Test Coverage Map (Ratio: {test_ratio:.2f})",
            box=ROUNDED,
            header_style="bold magenta",
        )
        cov_table.add_column("Symbol", style="bold")
        cov_table.add_column("Location", style="dim")
        cov_table.add_column("Status", justify="center")

        for s in symbol_map:
            st = s.get("status", "untested")
            st_style = (
                "bold green"
                if st == "tested"
                else ("bold yellow" if st == "partially tested" else "bold red")
            )
            cov_table.add_row(
                s.get("symbol", ""),
                f"{s.get('file_path', '')}:{s.get('line_number', '')}",
                Text(st, style=st_style),
            )

        if symbol_map:
            console.print(cov_table)
            console.print()
    except Exception:
        pass

    # 6. Suggested Fix and Patch Verification
    if patch:
        verif = patch.verification
        if verif and verif.verdict == "VERIFIED":
            v_badge = "[bold green]VERIFIED[/bold green]"
            v_border = "green"
        elif verif and verif.verdict == "PARTIAL":
            v_badge = "[bold yellow]PARTIAL[/bold yellow]"
            v_border = "yellow"
        else:
            v_badge = "[bold red]REJECTED[/bold red]"
            v_border = "red"

        diff_syntax = Syntax(patch.unified_diff, "diff", theme="monokai", line_numbers=False)
        patch_info = Text()
        patch_info.append(f"Target Finding: {patch.finding_id} ({patch.file_path})\n", style="bold")
        patch_info.append(f"Explanation: {patch.explanation}\n")
        patch_info.append(f"Patch Verification: {v_badge}\n", style="bold")
        if verif and verif.details:
            patch_info.append(f"Details: {verif.details}\n", style="dim")

        console.print(
            Panel(
                diff_syntax,
                title=f"[bold]Suggested Fix for Top Finding - {v_badge}[/bold]",
                subtitle=patch.file_path,
                border_style=v_border,
                box=ROUNDED,
            )
        )
        console.print()

    # 7. Agent Execution & Timeline Table
    exec_table = Table(title="Agent Execution & Concurrency Timeline", box=ROUNDED)
    exec_table.add_column("Agent", style="bold")
    exec_table.add_column("Status", justify="center")
    exec_table.add_column("Duration", justify="right")
    exec_table.add_column("Findings", justify="right")
    exec_table.add_column("Execution Mode", justify="center")

    for agent_name, res in sorted(state.agent_results.items()):
        status_style = "bold green" if res.status == "ok" else "bold red"
        exec_table.add_row(
            agent_name,
            Text(res.status, style=status_style),
            f"{res.duration_ms:.1f}ms",
            str(len(res.findings)),
            res.mode,
        )

    console.print(exec_table)
    console.print()
