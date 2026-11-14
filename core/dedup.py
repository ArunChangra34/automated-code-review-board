"""Deduplication module merging overlapping findings from multiple agents."""

from __future__ import annotations

import re

from core.models import Finding


def _tokenize_text(text: str) -> set[str]:
    """Tokenize text into lowercase alphanumeric words for token Jaccard similarity."""
    tokens = re.findall(r"\b[a-zA-Z0-9_-]+\b", text.lower())
    return set(tokens)


def token_jaccard_similarity(text1: str, text2: str) -> float:
    """Compute token Jaccard similarity between two text strings."""
    tokens1 = _tokenize_text(text1)
    tokens2 = _tokenize_text(text2)
    if not tokens1 or not tokens2:
        return 0.0
    intersection = tokens1.intersection(tokens2)
    union = tokens1.union(tokens2)
    return len(intersection) / len(union)


def are_findings_duplicates(f1: Finding, f2: Finding, similarity_threshold: float = 0.65) -> bool:
    """Determine whether two findings refer to the same defect."""
    # Must be in the same file
    if f1.file_path != f2.file_path or not f1.file_path:
        return False

    # Check line range overlap
    f1_start = f1.line_start or 0
    f1_end = f1.line_end or f1_start
    f2_start = f2.line_start or 0
    f2_end = f2.line_end or f2_start

    lines_overlap = not (f1_end < f2_start or f2_end < f1_start)
    if not lines_overlap:
        return False

    # Same rule ID is an immediate duplicate match
    if f1.rule_id == f2.rule_id:
        return True

    # Otherwise check semantic / title text similarity
    sim = token_jaccard_similarity(
        f"{f1.title} {f1.description}",
        f"{f2.title} {f2.description}",
    )
    return sim >= similarity_threshold


def merge_two_findings(primary: Finding, duplicate: Finding) -> Finding:
    """Merge duplicate finding into primary, preserving maximum severity and combining sources."""
    # Highest severity wins
    merged_severity = max(primary.severity, duplicate.severity)

    # Union reported_by
    combined_reporters = sorted(list(set(primary.reported_by + duplicate.reported_by)))

    # Concatenate citations if distinct
    citations = []
    for cit in (primary.evidence_source, duplicate.evidence_source):
        if cit and cit not in citations:
            citations.append(cit)
    merged_citation = " | ".join(citations) if citations else None

    # Higher confidence
    merged_confidence = max(primary.confidence, duplicate.confidence)

    # Pick longest, most descriptive recommendation
    rec = primary.recommendation
    if len(duplicate.recommendation) > len(rec):
        rec = duplicate.recommendation

    return Finding(
        id=primary.id,
        category=primary.category,
        severity=merged_severity,
        title=primary.title,
        description=primary.description,
        file_path=primary.file_path,
        line_start=min(primary.line_start or 0, duplicate.line_start or 0) or None,
        line_end=max(primary.line_end or 0, duplicate.line_end or 0) or None,
        code_snippet=primary.code_snippet or duplicate.code_snippet,
        rule_id=primary.rule_id,
        evidence_source=merged_citation,
        recommendation=rec,
        confidence=merged_confidence,
        reported_by=combined_reporters,
        corroborated_by=sorted(list(set(primary.corroborated_by + duplicate.corroborated_by))),
        priority_rank=primary.priority_rank,
    )


def deduplicate_findings(findings: list[Finding]) -> tuple[list[Finding], int]:
    """Deduplicate findings and return merged list and duplicate count."""
    if not findings:
        return [], 0

    deduped: list[Finding] = []
    merged_count = 0

    for candidate in findings:
        matched_idx = -1
        for idx, existing in enumerate(deduped):
            if are_findings_duplicates(existing, candidate):
                matched_idx = idx
                break

        if matched_idx >= 0:
            deduped[matched_idx] = merge_two_findings(deduped[matched_idx], candidate)
            merged_count += 1
        else:
            deduped.append(candidate)

    return deduped, merged_count
