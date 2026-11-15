"""Orchestrator managing concurrent fan-out, fan-in barrier, and pipeline execution."""

from __future__ import annotations

import asyncio
from typing import Any

from semantic_kernel import Kernel

from agents.diff_agent import DiffAgent
from agents.fix_suggestion_agent import FixSuggestionAgent
from agents.reviewer_manager import ReviewerManager
from agents.security_agent import SecurityAgent
from agents.style_agent import StyleAgent
from agents.test_coverage_agent import TestCoverageAgent
from config.settings import Settings, get_settings
from core.kernel_factory import create_kernel
from core.logging_setup import get_logger
from core.state import ChangeState

logger = get_logger("orchestrator")


class ReviewOrchestrator:
    """Coordinates fan-out execution of specialist agents and fan-in manager synthesis."""

    def __init__(
        self,
        kernel: Kernel | None = None,
        settings: Settings | None = None,
        coverage_report_path: str = "",
        fix_agent: Any | None = None,
    ):
        self.settings = settings or get_settings()
        self.kernel = kernel or create_kernel(self.settings)
        self.coverage_report_path = coverage_report_path

        # Instantiate specialist agents
        self.diff_agent = DiffAgent(kernel=self.kernel, settings=self.settings)
        self.style_agent = StyleAgent(kernel=self.kernel, settings=self.settings)
        self.security_agent = SecurityAgent(kernel=self.kernel, settings=self.settings)
        self.coverage_agent = TestCoverageAgent(
            kernel=self.kernel,
            settings=self.settings,
            coverage_report_path=coverage_report_path,
        )

        # Instantiate manager and fix-suggestion agent
        self.manager = ReviewerManager(kernel=self.kernel, settings=self.settings)
        self.fix_agent = fix_agent or FixSuggestionAgent(kernel=self.kernel, settings=self.settings)

    async def run_review(self, state: ChangeState) -> ChangeState:
        """Execute the multi-agent review pipeline across all stages."""
        logger.info("Initiating concurrent agent fan-out for change %s", state.change_id)

        # Stage 1: Fan-out - Run the four specialist agents concurrently
        specialists = [
            self.diff_agent,
            self.style_agent,
            self.security_agent,
            self.coverage_agent,
        ]

        # Concurrently execute all specialists; error isolation inside BaseAgent guarantees completion
        await asyncio.gather(*(agent.run(state) for agent in specialists))

        # Stage 2: Fan-in Barrier - Reviewer Manager consolidates and decides
        logger.info(
            "Fan-in barrier reached. Running Reviewer Manager for change %s", state.change_id
        )
        await self.manager.run(state)

        # Stage 3: Fix-Suggestion Agent (if present and rank-1 finding exists)
        if (
            self.fix_agent
            and state.consolidated_review
            and state.consolidated_review.priority_order
        ):
            top_finding = state.consolidated_review.priority_order[0]
            logger.info("Running Fix-Suggestion Agent on rank-1 finding: %s", top_finding.id)
            await self.fix_agent.run(state)

        logger.info(
            "Review completed for %s. Decision: %s, Score: %s/100",
            state.change_id,
            state.consolidated_review.decision if state.consolidated_review else "UNKNOWN",
            state.consolidated_review.merge_risk_score if state.consolidated_review else 0,
        )

        return state
