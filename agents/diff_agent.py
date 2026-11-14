"""Diff Agent analyzing files touched, change statistics, symbol extraction, and domain risk."""

from __future__ import annotations

from semantic_kernel import Kernel

from agents.base_agent import BaseAgent
from config.settings import Settings
from core.models import Category, Finding, Severity
from core.state import ChangeState
from plugins.diff_plugin import DiffPlugin


class DiffAgent(BaseAgent):
    """Specialist agent summarizing change structure, metrics, and risky functional domains."""

    def __init__(
        self,
        kernel: Kernel,
        settings: Settings | None = None,
        plugin: DiffPlugin | None = None,
    ):
        self.diff_plugin = plugin or DiffPlugin()
        instructions = (
            "You are the Diff Analysis Agent. Your responsibility is to summarize code changes, "
            "compute size metrics, identify modified roles, and detect high-risk functional domains."
        )
        super().__init__(
            name="diff_agent",
            description="Analyzes structural change statistics, modified files, and sensitive domains",
            instructions=instructions,
            category=Category.DIFF,
            kernel=kernel,
            plugins=[self.diff_plugin],
            settings=settings,
        )

    async def analyze_deterministic(self, state: ChangeState) -> list[Finding]:
        """Compute structural stats, populate ChangeState summary, and issue informational findings."""
        policy = self.settings.load_severity_policy()
        size_thresholds = policy.get("size_thresholds", {})

        summary = self.diff_plugin.summarize_change(state.files, size_thresholds=size_thresholds)
        await state.set_summary(summary)

        findings: list[Finding] = []

        # Rule DIF-SIZE-001: Large change advisory
        if summary.size_class in ("L", "XL"):
            finding = Finding(
                id=Finding.generate_id(Category.DIFF, "DIF-SIZE-001", None, 0),
                category=Category.DIFF,
                severity=Severity.INFO,
                title="Large Change Size Advisory",
                description=(
                    f"This pull request modifies {summary.lines_added + summary.lines_removed} lines "
                    f"across {summary.total_files} files (Size: {summary.size_class}). Large changes increase "
                    "review fatigue and defect escape rates."
                ),
                rule_id="DIF-SIZE-001",
                recommendation="Consider breaking down large modifications into smaller, self-contained commits or PRs.",
                confidence=1.0,
                reported_by=[self.name],
            )
            findings.append(finding)

        # Rule DIF-DEP-001: Dependency manifest change notification
        dep_files = [f.path for f in state.files if f.role == "dependency"]
        if dep_files:
            finding = Finding(
                id=Finding.generate_id(Category.DIFF, "DIF-DEP-001", dep_files[0], 1),
                category=Category.DIFF,
                severity=Severity.INFO,
                title="Dependency Manifest Modified",
                description=f"Package dependency manifests were modified: {', '.join(dep_files)}.",
                file_path=dep_files[0],
                line_start=1,
                rule_id="DIF-DEP-001",
                recommendation="Verify security advisories, licensing terms, and version lock constraints for updated dependencies.",
                confidence=1.0,
                reported_by=[self.name],
            )
            findings.append(finding)

        # Rule DIF-RISK-001: Sensitive domain notification
        if summary.risk_areas:
            finding = Finding(
                id=Finding.generate_id(Category.DIFF, "DIF-RISK-001", None, 0),
                category=Category.DIFF,
                severity=Severity.INFO,
                title="Sensitive Risk Areas Touched",
                description=f"Change touches security-sensitive functional domains: {', '.join(summary.risk_areas)}.",
                rule_id="DIF-RISK-001",
                recommendation="Prioritize in-depth security and boundary validation reviews for changes impacting these modules.",
                confidence=1.0,
                reported_by=[self.name],
            )
            findings.append(finding)

        return findings
