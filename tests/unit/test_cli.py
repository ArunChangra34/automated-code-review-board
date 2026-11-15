"""Unit tests for CLI interface using Typer CliRunner."""

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner(env={"COLUMNS": "160"})


def test_cli_help():
    """Verify that CLI help command returns 0 and displays review and demo subcommands."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "review" in result.stdout
    assert "demo" in result.stdout


def test_cli_demo_runs_successfully():
    """Verify that demo command runs all sample diffs and generates summary table."""
    result = runner.invoke(app, ["demo"])
    assert result.exit_code == 0
    assert "01_clean_change.diff" in result.stdout
    assert "02_sql_injection_and_secret.diff" in result.stdout
    assert "APPROVE" in result.stdout
    assert "REQUEST_CHANGES" in result.stdout


def test_cli_review_diff_file(tmp_path):
    """Verify review command with --diff and custom output directory."""
    out_dir = tmp_path / "custom_out"
    result = runner.invoke(
        app,
        [
            "review",
            "--diff",
            "samples/diffs/01_clean_change.diff",
            "--output-dir",
            str(out_dir),
            "--format",
            "both",
        ],
    )
    assert result.exit_code == 0
    assert (out_dir / "review.md").exists()
    assert (out_dir / "review.json").exists()


def test_cli_fail_on_request_changes():
    """Verify --fail-on-request-changes exits with code 1 when REQUEST_CHANGES."""
    result = runner.invoke(
        app,
        [
            "review",
            "--diff",
            "samples/diffs/02_sql_injection_and_secret.diff",
            "--fail-on-request-changes",
        ],
    )
    assert result.exit_code == 1
