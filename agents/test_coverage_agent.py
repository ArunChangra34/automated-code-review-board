"""Test-Coverage Agent analyzing test adequacy, symbol coverage maps, and assertions."""

from __future__ import annotations

from typing import Any

from semantic_kernel import Kernel

from agents.base_agent import BaseAgent
from config.settings import Settings
from core.models import Category, Finding
from core.state import ChangeState
from plugins.coverage_plugin import CoveragePlugin


class TestCoverageAgent(BaseAgent):
    """Specialist agent determining whether code changes include sufficient, qualified tests."""

    def __init__(
        self,
        kernel: Kernel,
        settings: Settings | None = None,
        plugin: CoveragePlugin | None = None,
        coverage_report_path: str = "",
    ):
        self.coverage_plugin = plugin or CoveragePlugin()
        self.coverage_report_path = coverage_report_path
        self.last_analysis_metrics: dict[str, Any] = {}
        instructions = (
            "You are the Test-Coverage Agent. Inspect diffs to verify whether newly introduced "
            "symbols, business logic, and error conditions have corresponding unit tests. "
            "Evaluate test quality signals including assertion presence and error-path coverage."
        )
        super().__init__(
            name="test_coverage_agent",
            description="Evaluates test coverage ratios, symbol mapping, and test quality assertions",
            instructions=instructions,
            category=Category.TEST_COVERAGE,
            kernel=kernel,
            plugins=[self.coverage_plugin],
            settings=settings,
        )

    async def analyze_deterministic(self, state: ChangeState) -> list[Finding]:
        """Execute deterministic test coverage analysis and return identified gaps."""
        analysis = self.coverage_plugin.analyze_coverage(
            state.files,
            coverage_report_path=self.coverage_report_path,
        )
        self.last_analysis_metrics = analysis
        findings: list[Finding] = analysis.get("findings", [])
        return findings
