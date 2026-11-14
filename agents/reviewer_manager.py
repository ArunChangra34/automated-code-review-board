"""Reviewer Manager consolidating specialist findings, deduplicating, corroborating, and deciding."""

from __future__ import annotations

from semantic_kernel import Kernel

from agents.base_agent import BaseAgent
from config.settings import Settings
from core.dedup import deduplicate_findings
from core.models import Category, Finding
from core.ranking import build_consolidated_review
from core.state import ChangeState


class ReviewerManager(BaseAgent):
    """Manager agent executing fan-in aggregation, deduplication, ranking, and merge decision."""

    def __init__(
        self,
        kernel: Kernel,
        settings: Settings | None = None,
    ):
        instructions = (
            "You are the Reviewer Manager. You synthesize findings across Diff, Style, Security, "
            "and Test-Coverage specialist agents. Eliminate redundancies, corroborate overlapping issues, "
            "apply the severity policy rubric, and output a definitive merge recommendation."
        )
        super().__init__(
            name="reviewer_manager",
            description="Aggregates and deduplicates specialist findings to determine merge approval",
            instructions=instructions,
            category=Category.DIFF,
            kernel=kernel,
            settings=settings,
        )

    async def analyze_deterministic(self, state: ChangeState) -> list[Finding]:
        """Aggregate all specialist findings, deduplicate, corroborate, and decide."""
        raw_findings: list[Finding] = []
        for result in state.agent_results.values():
            raw_findings.extend(result.findings)

        # 1. Deduplicate
        deduped_findings, duplicates_removed = deduplicate_findings(raw_findings)

        # 2. Load severity policy
        policy = self.settings.load_severity_policy()

        # 3. Build Consolidated Review
        review = build_consolidated_review(
            findings=deduped_findings,
            agent_status=dict(state.agent_status),
            duplicates_removed=duplicates_removed,
            policy=policy,
        )

        # 4. Save to shared change state
        await state.set_consolidated_review(review)

        return review.priority_order
