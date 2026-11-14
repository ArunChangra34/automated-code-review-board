"""Severity ranking, corroboration scoring, and merge decision engine."""

from __future__ import annotations

from typing import Any

from core.models import Category, ConsolidatedReview, Finding, Severity

# Default fallback policy if none loaded
_DEFAULT_WEIGHTS = {
    "CRITICAL": 40,
    "HIGH": 20,
    "MEDIUM": 8,
    "LOW": 2,
    "INFO": 0,
}
_DEFAULT_CATEGORY_PRIORITY = ["security", "test_coverage", "style", "diff"]


def identify_corroborations(findings: list[Finding]) -> list[Finding]:
    """Identify cross-agent corroborated findings flagged at the same location by different agents."""
    corroborated: list[Finding] = []

    for i, f1 in enumerate(findings):
        reporters: set[str] = set(f1.reported_by)

        for j, f2 in enumerate(findings):
            if i == j:
                continue
            # Same file and nearby line range (within 5 lines)
            if f1.file_path and f1.file_path == f2.file_path:
                l1 = f1.line_start or 0
                l2 = f2.line_start or 0
                if abs(l1 - l2) <= 5:
                    reporters.update(f2.reported_by)

        unique_reporters = sorted(list(reporters))
        if len(unique_reporters) > 1:
            # Multi-agent corroboration detected
            boosted_confidence = min(1.0, f1.confidence + 0.10 * (len(unique_reporters) - 1))
            updated = f1.model_copy(
                update={
                    "corroborated_by": unique_reporters,
                    "confidence": round(boosted_confidence, 2),
                }
            )
            corroborated.append(updated)
        else:
            corroborated.append(f1)

    return corroborated


def calculate_merge_risk_score(
    findings: list[Finding],
    policy: dict[str, Any],
) -> int:
    """Calculate aggregate merge risk score (0-100) using policy weights and corroboration factors."""
    weights = policy.get("weights", _DEFAULT_WEIGHTS)
    thresholds = policy.get("thresholds", {})
    max_score = int(thresholds.get("max_score", 100))
    multiplier = thresholds.get("corroboration_multiplier", 0.10)

    raw_score = 0
    corroborated_count = 0

    for f in findings:
        weight = weights.get(f.severity.value, 0)
        raw_score += weight
        if len(f.corroborated_by) > 1:
            corroborated_count += 1

    if corroborated_count > 0:
        boost = 1.0 + (multiplier * corroborated_count)
        total_score = int(round(raw_score * boost))
    else:
        total_score = raw_score

    return min(max_score, max(0, total_score))


def rank_findings(
    findings: list[Finding],
    policy: dict[str, Any],
) -> list[Finding]:
    """Sort findings by severity, corroboration, confidence, and category priority."""
    cat_order = policy.get("category_priority", _DEFAULT_CATEGORY_PRIORITY)
    cat_rank = {cat: idx for idx, cat in enumerate(cat_order)}

    def sort_key(f: Finding) -> tuple[int, int, float, int, str, int]:
        # Severity rank (higher is worse -> negate for descending)
        sev_val = -f.severity.rank
        # Corroboration bonus (corroborated first)
        corrob_val = -len(f.corroborated_by)
        # Confidence (higher first)
        conf_val = -f.confidence
        # Category priority (lower index is higher priority)
        cat_val = cat_rank.get(f.category.value, 99)
        file_val = f.file_path or ""
        line_val = f.line_start or 0
        return (sev_val, corrob_val, conf_val, cat_val, file_val, line_val)

    sorted_list = sorted(findings, key=sort_key)

    # Assign sequential 1-based priority rank
    ranked: list[Finding] = []
    for rank_idx, item in enumerate(sorted_list, start=1):
        ranked.append(item.model_copy(update={"priority_rank": rank_idx}))

    return ranked


def evaluate_merge_decision(
    findings: list[Finding],
    policy: dict[str, Any],
) -> tuple[str, str, int]:
    """Evaluate severity policy rules to determine APPROVE or REQUEST_CHANGES."""
    blocking_severities = set(policy.get("blocking_severities", ["CRITICAL", "HIGH"]))
    thresholds = policy.get("thresholds", {})
    req_changes_threshold = thresholds.get("request_changes_score", 30)

    score = calculate_merge_risk_score(findings, policy)

    # Check for blocking severities
    blocking_findings = [f for f in findings if f.severity.value in blocking_severities]

    if blocking_findings:
        decision = "REQUEST_CHANGES"
        reasons = [
            f"Rank #{f.priority_rank} [{f.severity.value}]: {f.title} in {f.file_path or 'diff'}"
            for f in blocking_findings[:3]
        ]
        reason_str = (
            f"Merge changes requested due to {len(blocking_findings)} blocking issue(s) "
            f"exceeding risk tolerance (Merge Risk Score: {score}/100). "
            f"Critical blockers: {'; '.join(reasons)}. "
            "Remediation must be applied before merging."
        )
    elif score >= req_changes_threshold:
        decision = "REQUEST_CHANGES"
        reason_str = (
            f"Merge changes requested because the cumulative risk score of non-blocking issues "
            f"({score}/100) exceeds the repository threshold ({req_changes_threshold}/100). "
            "Resolve maintainability, style, or test quality warnings before merging."
        )
    else:
        decision = "APPROVE"
        remaining_count = len(findings)
        reason_str = (
            f"Pull request meets acceptance criteria with a low merge risk score of {score}/100. "
            f"{remaining_count} non-blocking advisory note(s) identified for optional improvement."
        )

    return decision, reason_str, score


def build_consolidated_review(
    findings: list[Finding],
    agent_status: dict[str, str],
    duplicates_removed: int,
    policy: dict[str, Any],
) -> ConsolidatedReview:
    """Build complete ConsolidatedReview object from deduplicated findings and policy."""
    corroborated_findings = identify_corroborations(findings)
    ranked_findings = rank_findings(corroborated_findings, policy)
    decision, reason, score = evaluate_merge_decision(ranked_findings, policy)

    findings_by_severity: dict[Severity, list[Finding]] = {s: [] for s in Severity}
    for f in ranked_findings:
        findings_by_severity[f.severity].append(f)

    corroborated_count = sum(1 for f in ranked_findings if len(f.corroborated_by) > 1)

    stats = {
        "total_findings": len(ranked_findings),
        "duplicates_removed": duplicates_removed,
        "corroborated_findings": corroborated_count,
        "counts_by_severity": {s.value: len(findings_by_severity[s]) for s in Severity},
        "counts_by_category": {
            cat.value: sum(1 for f in ranked_findings if f.category == cat) for cat in Category
        },
    }

    return ConsolidatedReview(
        decision=decision,  # type: ignore[arg-type]
        decision_reason=reason,
        merge_risk_score=score,
        findings_by_severity=findings_by_severity,
        priority_order=ranked_findings,
        stats=stats,
        agent_status=agent_status,
    )
