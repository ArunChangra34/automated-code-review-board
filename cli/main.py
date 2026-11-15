"""Command-line interface for the Automated Code Review Board."""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from typing import Optional

import typer
from rich.box import ROUNDED
from rich.console import Console
from rich.table import Table
from rich.text import Text

from config.settings import get_settings
from core.diff_loader import load_diff_from_file, load_diff_from_git, load_diff_from_stdin
from core.logging_setup import configure_logging, get_logger
from core.models import Severity
from core.orchestrator import ReviewOrchestrator
from reporting.console_report import print_console_report
from reporting.json_report import generate_json_report
from reporting.markdown_report import generate_markdown_report

app = typer.Typer(
    help="Automated Code Review Board - Multi-Agent Unified Diff Review System",
    no_args_is_help=True,
)
logger = get_logger("cli")
console = Console()


@app.command(name="review")
def review(
    diff: Optional[Path] = typer.Option(
        None, "--diff", "-d", help="Path to unified diff file to review"
    ),
    git: Optional[str] = typer.Option(
        None,
        "--git",
        "-g",
        help="Git revision range to review (e.g. 'main..feature' or 'HEAD~1..HEAD')",
    ),
    stdin: bool = typer.Option(
        False, "--stdin", help="Read unified diff text directly from standard input"
    ),
    mode: str = typer.Option(
        "offline",
        "--mode",
        "-m",
        help="Execution mode: 'offline' (deterministic) or 'llm' (model-augmented)",
    ),
    coverage_report: Optional[str] = typer.Option(
        None, "--coverage-report", help="Path to external coverage report (XML or JSON)"
    ),
    output_dir: Optional[Path] = typer.Option(
        None, "--output-dir", "-o", help="Target directory for output review artifacts"
    ),
    report_format: str = typer.Option(
        "both",
        "--format",
        "-f",
        help="Report formats to generate: 'md', 'json', or 'both'",
    ),
    fail_on_request_changes: bool = typer.Option(
        False,
        "--fail-on-request-changes",
        help="Exit with non-zero exit code (1) if recommendation is REQUEST_CHANGES",
    ),
    simulate_failure: Optional[str] = typer.Option(
        None,
        "--simulate-failure",
        help="Simulate failure for named agent (e.g. 'security' or 'style')",
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable verbose debug logging output"
    ),
) -> None:
    """Execute multi-agent automated review on a unified diff."""
    log_level = "DEBUG" if verbose else "INFO"
    configure_logging(log_level)

    # 1. Diff source selection
    inputs_count = sum([bool(diff), bool(git), stdin])
    if inputs_count == 0:
        console.print(
            "[bold red]Error:[/bold red] You must specify a diff source: "
            "`--diff <path>`, `--git <range>`, or `--stdin`."
        )
        raise typer.Exit(code=2)
    if inputs_count > 1:
        console.print(
            "[bold red]Error:[/bold red] Please specify only one of `--diff`, `--git`, or `--stdin`."
        )
        raise typer.Exit(code=2)

    try:
        if stdin:
            raw_text = sys.stdin.read()
            if not raw_text.strip():
                console.print("[bold red]Error:[/bold red] Empty diff received from stdin.")
                raise typer.Exit(code=2)
            state = load_diff_from_stdin(raw_text)
        elif diff:
            if not diff.exists():
                console.print(f"[bold red]Error:[/bold red] Diff file not found: {diff}")
                raise typer.Exit(code=2)
            state = load_diff_from_file(diff)
        elif git:
            state = load_diff_from_git(git)
        else:
            raise typer.Exit(code=2)
    except Exception as exc:
        console.print(f"[bold red]Failed to load diff:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc

    # 2. Configuration & Settings
    settings = get_settings()
    settings.mode = "llm" if mode.lower() == "llm" else "offline"
    if simulate_failure:
        settings.simulate_failure = simulate_failure

    # 3. Execution
    orchestrator = ReviewOrchestrator(
        settings=settings,
        coverage_report_path=coverage_report or "",
    )

    with console.status("[bold green]Running Automated Review Board agents..."):
        state = asyncio.run(orchestrator.run_review(state))

    # 4. Console output
    print_console_report(state, console=console)

    # 5. Output artifacts
    target_dir = output_dir or (Path("output") / state.change_id)
    target_dir.mkdir(parents=True, exist_ok=True)

    fmt = report_format.lower()
    written_files: list[Path] = []
    if fmt in ("md", "both"):
        md_path = target_dir / "review.md"
        md_content = generate_markdown_report(state, mode=settings.mode)
        md_path.write_text(md_content, encoding="utf-8")
        written_files.append(md_path)

    if fmt in ("json", "both"):
        json_path = target_dir / "review.json"
        json_content = generate_json_report(state)
        json_path.write_text(json_content, encoding="utf-8")
        written_files.append(json_path)

    for wf in written_files:
        console.print(f"Report generated: [bold cyan]{wf}[/bold cyan]")

    # 6. CI Exit Code check
    if (
        fail_on_request_changes
        and state.consolidated_review
        and state.consolidated_review.decision == "REQUEST_CHANGES"
    ):
        console.print(
            "\n[bold red]CI Check Failed:[/bold red] Review recommendation is REQUEST_CHANGES."
        )
        raise typer.Exit(code=1)


@app.command(name="demo")
def demo(
    output_dir: Path = typer.Option(
        Path("output"),
        "--output-dir",
        "-o",
        help="Directory to store demo review reports",
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable verbose debug logging output"
    ),
) -> None:
    """Run all 5 standard sample diffs in offline mode and display the summary table."""
    log_level = "DEBUG" if verbose else "WARNING"
    configure_logging(log_level)

    samples_dir = Path("samples") / "diffs"
    if not samples_dir.exists():
        console.print(f"[bold red]Error:[/bold red] Samples directory not found at {samples_dir}")
        raise typer.Exit(code=1)

    sample_files = sorted(samples_dir.glob("*.diff"))
    if not sample_files:
        console.print(f"[bold red]Error:[/bold red] No .diff files found in {samples_dir}")
        raise typer.Exit(code=1)

    settings = get_settings()
    settings.mode = "offline"
    settings.simulate_failure = None

    table = Table(
        title="Automated Code Review Board - Demo Execution Summary",
        box=ROUNDED,
        header_style="bold cyan",
    )
    table.add_column("Sample Diff", style="bold", no_wrap=True)
    table.add_column("Decision", justify="center", no_wrap=True)
    table.add_column("Risk Score", justify="center", no_wrap=True)
    table.add_column("Findings (C/H/M/L/I)", justify="center", no_wrap=True)
    table.add_column("Patch Verdict", justify="center", no_wrap=True)
    table.add_column("Duration", justify="right", no_wrap=True)

    console.print("\n[bold]Running multi-agent code reviews on all 5 sample diffs...[/bold]\n")

    overall_start = time.perf_counter()

    for sf in sample_files:
        start_t = time.perf_counter()
        state = load_diff_from_file(sf)
        orchestrator = ReviewOrchestrator(settings=settings)
        state = asyncio.run(orchestrator.run_review(state))
        elapsed = time.perf_counter() - start_t

        review = state.consolidated_review
        if not review:
            continue

        # Save artifacts
        sample_out = output_dir / sf.stem
        sample_out.mkdir(parents=True, exist_ok=True)
        (sample_out / "review.md").write_text(
            generate_markdown_report(state, mode="offline"), encoding="utf-8"
        )
        (sample_out / "review.json").write_text(generate_json_report(state), encoding="utf-8")

        # Table row details
        if review.decision == "APPROVE":
            dec_text = Text("APPROVE", style="bold green")
        else:
            dec_text = Text("REQUEST_CHANGES", style="bold red")

        score_text = f"{review.merge_risk_score}/100"

        c_cnt = len(review.findings_by_severity.get(Severity.CRITICAL, []))
        h_cnt = len(review.findings_by_severity.get(Severity.HIGH, []))
        m_cnt = len(review.findings_by_severity.get(Severity.MEDIUM, []))
        l_cnt = len(review.findings_by_severity.get(Severity.LOW, []))
        i_cnt = len(review.findings_by_severity.get(Severity.INFO, []))
        counts_str = f"{c_cnt}/{h_cnt}/{m_cnt}/{l_cnt}/{i_cnt}"

        patch = state.suggested_patch or review.suggested_patch
        if patch and patch.verification:
            verdict = patch.verification.verdict
            v_style = (
                "bold green"
                if verdict == "VERIFIED"
                else ("bold yellow" if verdict == "PARTIAL" else "bold red")
            )
            patch_text = Text(verdict, style=v_style)
        else:
            patch_text = Text("N/A", style="dim")

        table.add_row(
            sf.name,
            dec_text,
            score_text,
            counts_str,
            patch_text,
            f"{elapsed:.2f}s",
        )

    total_time = time.perf_counter() - overall_start

    console.print(table)
    console.print(
        f"\n[green]Demo completed in {total_time:.2f}s.[/green] "
        f"Detailed reports written to [bold cyan]{output_dir}/[/bold cyan]\n"
    )


if __name__ == "__main__":
    app()
