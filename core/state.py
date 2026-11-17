"""Shared change-state object providing shared memory across agents."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, PrivateAttr

from core.models import (
    AgentResult,
    ChangeSummary,
    ConsolidatedReview,
    FileChange,
    Finding,
    FixSuggestion,
    SuggestedPatch,
    TimelineEvent,
)


class ChangeState(BaseModel):
    """Shared state object representing a code review pipeline run."""

    change_id: str = Field(description="Unique identifier for the review request")
    submitted_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = Field(description="Origin description: file path, git commit range, or stdin")
    raw_diff: str = Field(description="Raw unified diff text")
    files: list[FileChange] = Field(default_factory=list, description="Parsed file changes")

    # Analysis results populated by agents
    summary: ChangeSummary | None = Field(default=None, description="Summary from Diff Agent")
    risk_areas: list[str] = Field(default_factory=list, description="High-risk domains detected")

    # Thread/agent slots: each agent writes only to its assigned key
    agent_results: dict[str, AgentResult] = Field(
        default_factory=dict, description="Agent execution results indexed by agent name"
    )
    agent_status: dict[str, str] = Field(
        default_factory=dict, description="Status summary per agent (ok/degraded/failed/timeout)"
    )

    # Consolidated output
    consolidated_review: ConsolidatedReview | None = Field(
        default=None, description="Final manager review and merge recommendation"
    )
    suggested_patch: SuggestedPatch | None = Field(
        default=None, description="Proposed verified fix for top finding"
    )

    # Per-finding fix suggestions (populated by FixSuggestionAgent in LLM/always mode)
    fix_suggestions: list[FixSuggestion] = Field(
        default_factory=list,
        description="Fix suggestions for each eligible finding, in priority order",
    )

    # Timeline of concurrent events
    timeline: list[TimelineEvent] = Field(
        default_factory=list, description="Execution timeline of agents"
    )

    # Concurrency control
    _lock: asyncio.Lock = PrivateAttr(default_factory=asyncio.Lock)

    @property
    def all_findings(self) -> list[Finding]:
        """Aggregate list of findings from all completed agent results."""
        findings: list[Finding] = []
        for result in self.agent_results.values():
            findings.extend(result.findings)
        return findings

    async def record_agent_start(self, agent_name: str) -> None:
        """Record the start of an agent's execution."""
        async with self._lock:
            self.timeline.append(TimelineEvent(agent_name=agent_name, event="started"))

    async def record_agent_result(self, result: AgentResult) -> None:
        """Safely record the result of an agent run."""
        async with self._lock:
            self.agent_results[result.agent_name] = result
            self.agent_status[result.agent_name] = result.status
            self.timeline.append(
                TimelineEvent(
                    agent_name=result.agent_name,
                    event="completed" if result.status in ("ok", "degraded") else "failed",
                    duration_ms=result.duration_ms,
                    details=result.error,
                )
            )

    async def set_summary(self, summary: ChangeSummary) -> None:
        """Set change summary and copy detected risk areas to state."""
        async with self._lock:
            self.summary = summary
            self.risk_areas = list(set(self.risk_areas + summary.risk_areas))

    async def set_consolidated_review(self, review: ConsolidatedReview) -> None:
        """Set final consolidated review."""
        async with self._lock:
            self.consolidated_review = review

    async def set_suggested_patch(self, patch: SuggestedPatch) -> None:
        """Set proposed verified fix patch."""
        async with self._lock:
            self.suggested_patch = patch
            if self.consolidated_review:
                self.consolidated_review.suggested_patch = patch

    async def set_fix_suggestions(self, suggestions: list[FixSuggestion]) -> None:
        """Set the full list of per-finding fix suggestions."""
        async with self._lock:
            self.fix_suggestions = suggestions
            if self.consolidated_review:
                self.consolidated_review.fix_suggestions = suggestions

    def get_snapshot(self) -> dict[str, Any]:
        """Get a read-only dictionary snapshot of the current state."""
        return self.model_dump()
