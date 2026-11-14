"""Semantic Kernel plugin for grounded retrieval against the local knowledge base."""

from __future__ import annotations

import json
from typing import Annotated

from semantic_kernel.functions import kernel_function

from core.retrieval import KnowledgeBase, get_knowledge_base


class RetrievalPlugin:
    """Plugin providing grounding search and rule lookup tools to agents."""

    def __init__(self, kb: KnowledgeBase | None = None):
        self.kb = kb or get_knowledge_base()

    @kernel_function(
        name="search_knowledge_base",
        description="Search engineering standards and security knowledge base for rules and guidance",
    )
    def search_knowledge_base(
        self,
        query: Annotated[str, "Search query keywords or rule identifier"],
        category_filter: Annotated[
            str, "Optional category filter: style, security, or testing"
        ] = "",
    ) -> str:
        """Search knowledge base and return matching citations and excerpts in JSON."""
        cat = category_filter.strip().lower() if category_filter else None
        results = self.kb.search(query, top_k=3, category_filter=cat)
        if not results:
            return json.dumps({"status": "no_results", "query": query, "matches": []})

        matches = []
        for chunk, score in results:
            matches.append(
                {
                    "rule_id": chunk.rule_id,
                    "section": chunk.section,
                    "citation": chunk.citation,
                    "score": round(score, 4),
                    "summary": chunk.content[:300],
                }
            )
        return json.dumps({"status": "ok", "query": query, "matches": matches}, indent=2)

    @kernel_function(
        name="lookup_rule_citation",
        description="Look up exact rule citation and standard remediation for a known rule ID",
    )
    def lookup_rule_citation(
        self,
        rule_id: Annotated[str, "Canonical rule code e.g. SEC-SQLI-001 or STY-NAME-001"],
    ) -> str:
        """Fetch exact rule definition and evidence citation."""
        chunk = self.kb.lookup_rule(rule_id.strip())
        if not chunk:
            return json.dumps({"status": "not_found", "rule_id": rule_id})

        return json.dumps(
            {
                "status": "ok",
                "rule_id": chunk.rule_id,
                "section": chunk.section,
                "citation": chunk.citation,
                "content": chunk.content,
            },
            indent=2,
        )
