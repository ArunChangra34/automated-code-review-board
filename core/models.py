"""Data models for Automated Code Review Board."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class Severity(str, Enum):
    """Finding severity levels in descending order of risk."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"

    @property
    def rank(self) -> int:
        """Numerical rank for sorting (higher rank = higher risk)."""
        ranks = {
            Severity.CRITICAL: 5,
            Severity.HIGH: 4,
            Severity.MEDIUM: 3,
            Severity.LOW: 2,
            Severity.INFO: 1,
        }
        return ranks[self]

    def __lt__(self, other: Any) -> bool:
        if isinstance(other, Severity):
            return self.rank < other.rank
        return NotImplemented

    def __le__(self, other: Any) -> bool:
        if isinstance(other, Severity):
            return self.rank <= other.rank
        return NotImplemented

    def __gt__(self, other: Any) -> bool:
        if isinstance(other, Severity):
            return self.rank > other.rank
        return NotImplemented

    def __ge__(self, other: Any) -> bool:
        if isinstance(other, Severity):
            return self.rank >= other.rank
        return NotImplemented


class Category(str, Enum):
    """Review category matching the specialist agent disciplines."""

    DIFF = "diff"
    STYLE = "style"
    SECURITY = "security"
    TEST_COVERAGE = "test_coverage"


class Finding(BaseModel):
    """An individual issue or observation identified by a review agent."""

    id: str = Field(description="Deterministic hash of category, rule_id, file, and line_start")
    category: Category = Field(description="Review agent category")
    severity: Severity = Field(description="Severity rating")
    title: str = Field(description="Concise description of the finding")
    description: str = Field(description="Detailed explanation of the issue")
    file_path: str | None = Field(default=None, description="Path to affected file")
    line_start: int | None = Field(default=None, description="Starting line number")
    line_end: int | None = Field(default=None, description="Ending line number")
    code_snippet: str | None = Field(default=None, description="Code snippet with secrets redacted")
    rule_id: str = Field(description="Canonical rule code e.g. SEC-SQLI-001")
    evidence_source: str | None = Field(
        default=None, description="Citation path into knowledge base (doc#section)"
    )
    recommendation: str = Field(description="Remediation steps for the developer")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score")
    reported_by: list[str] = Field(default_factory=list, description="Names of reporting agents")
    corroborated_by: list[str] = Field(
        default_factory=list, description="Agents that independently corroborated this"
    )
    priority_rank: int | None = Field(
        default=None, description="Ordered priority assigned by manager"
    )

    @classmethod
    def generate_id(
        cls,
        category: Category | str,
        rule_id: str,
        file_path: str | None,
        line_start: int | None,
    ) -> str:
        """Generate a stable, unique identifier for deduplication."""
        cat_str = category.value if isinstance(category, Category) else str(category)
        raw_key = f"{cat_str}:{rule_id}:{file_path or 'none'}:{line_start or 0}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:12]

    @field_validator("id", mode="before")
    @classmethod
    def ensure_id(cls, v: Any, values: Any) -> str:
        if v:
            return str(v)
        return "finding-" + hashlib.sha256(str(datetime.now().timestamp()).encode()).hexdigest()[:8]


class LineInfo(BaseModel):
    """Information on an individual line within a hunk."""

    line_number: int
    content: str


class HunkInfo(BaseModel):
    """Unified diff hunk metadata and contents."""

    source_start: int
    source_length: int
    target_start: int
    target_length: int
    added_lines: list[LineInfo] = Field(default_factory=list)
    removed_lines: list[LineInfo] = Field(default_factory=list)
    context_lines: list[LineInfo] = Field(default_factory=list)
    raw_hunk: str = ""


class FileChange(BaseModel):
    """Changes applied to a single file in the diff."""

    path: str
    change_type: Literal["added", "modified", "deleted", "renamed"]
    language: str
    role: Literal["source", "test", "config", "docs", "dependency", "build", "other"]
    lines_added: int = 0
    lines_removed: int = 0
    hunks: list[HunkInfo] = Field(default_factory=list)
    is_binary: bool = False


class ChangeSummary(BaseModel):
    """Summary of entire changeset computed by Diff Agent."""

    title: str = "Pull Request Change Summary"
    intent_summary: str
    files: list[FileChange] = Field(default_factory=list)
    total_files: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    languages: list[str] = Field(default_factory=list)
    size_class: Literal["XS", "S", "M", "L", "XL"] = "S"
    risk_areas: list[str] = Field(default_factory=list)
    detected_symbols: list[str] = Field(default_factory=list)


class AgentResult(BaseModel):
    """Execution output from a single agent."""

    agent_name: str
    status: Literal["ok", "degraded", "failed", "timeout"]
    findings: list[Finding] = Field(default_factory=list)
    duration_ms: float = 0.0
    error: str | None = None
    mode: Literal["offline", "llm"] = "offline"


class PatchVerification(BaseModel):
    """Machine verification result of a proposed fix patch."""

    applies_cleanly: bool
    syntax_ok: bool
    original_finding_resolved: bool
    new_findings_introduced: list[Finding] = Field(default_factory=list)
    verdict: Literal["VERIFIED", "PARTIAL", "REJECTED"]
    details: str = ""


class SuggestedPatch(BaseModel):
    """Concrete remediation patch for the top finding."""

    finding_id: str
    file_path: str
    unified_diff: str
    explanation: str
    new_imports: list[str] = Field(default_factory=list)
    followups: list[str] = Field(default_factory=list)
    verification: PatchVerification | None = None


class TimelineEvent(BaseModel):
    """Timeline entry for recording agent execution lifecycle."""

    agent_name: str
    event: Literal["started", "completed", "failed", "timed_out"]
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    duration_ms: float | None = None
    details: str | None = None


def _default_findings_by_severity() -> dict[Severity, list[Finding]]:
    return {s: [] for s in Severity}


class ConsolidatedReview(BaseModel):
    """Consolidated review output assembled by the Reviewer Manager."""

    decision: Literal["APPROVE", "REQUEST_CHANGES"]
    decision_reason: str
    merge_risk_score: int = Field(ge=0, le=100)
    findings_by_severity: dict[Severity, list[Finding]] = Field(
        default_factory=_default_findings_by_severity
    )
    priority_order: list[Finding] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)
    agent_status: dict[str, str] = Field(default_factory=dict)
    suggested_patch: SuggestedPatch | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
