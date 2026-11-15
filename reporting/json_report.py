"""JSON serialization report for Automated Code Review Board."""

from __future__ import annotations

import json
from typing import Any

from core.state import ChangeState


def generate_json_report(state: ChangeState, indent: int = 2) -> str:
    """Serialize full ConsolidatedReview + ChangeState snapshot as formatted JSON string."""
    snapshot: dict[str, Any] = {
        "change_id": state.change_id,
        "submitted_at": state.submitted_at,
        "source": state.source,
        "summary": state.summary.model_dump(mode="json") if state.summary else None,
        "risk_areas": state.risk_areas,
        "agent_status": state.agent_status,
        "agent_results": {
            name: res.model_dump(mode="json") for name, res in state.agent_results.items()
        },
        "timeline": [event.model_dump(mode="json") for event in state.timeline],
        "consolidated_review": (
            state.consolidated_review.model_dump(mode="json") if state.consolidated_review else None
        ),
        "suggested_patch": (
            state.suggested_patch.model_dump(mode="json") if state.suggested_patch else None
        ),
    }

    return json.dumps(snapshot, indent=indent, default=str)
