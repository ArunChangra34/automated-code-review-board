"""Unit tests for offline retrieval engine and Semantic Kernel retrieval plugin."""

import json

from core.retrieval import KnowledgeBase
from plugins.retrieval_plugin import RetrievalPlugin


def test_knowledge_base_loading():
    """Verify that knowledge base loads documents and creates indices."""
    kb = KnowledgeBase()
    assert len(kb.chunks) > 10, f"Expected >10 chunks, found {len(kb.chunks)}"
    assert len(kb.rule_index) > 10, f"Expected >10 indexed rules, found {len(kb.rule_index)}"


def test_rule_id_exact_lookup():
    """Verify >=90% success rate on known rule-ID lookups."""
    kb = KnowledgeBase()
    test_rules = [
        "SEC-SQLI-001",
        "SEC-SECRET-001",
        "SEC-SECRET-002",
        "SEC-CMDI-001",
        "SEC-DESER-001",
        "SEC-EVAL-001",
        "SEC-CRYPTO-001",
        "SEC-TLS-001",
        "STY-LEN-001",
        "STY-NAME-001",
        "STY-NAME-002",
        "STY-DOC-001",
        "STY-COMPLEX-001",
        "STY-EXCEPT-001",
        "STY-IMPORT-001",
        "TST-UNTESTED-001",
        "TST-PARTIAL-001",
        "TST-RATIO-001",
        "RECIPE-SEC-SQLI-001",
        "RECIPE-SEC-SECRET-001",
    ]

    success_count = sum(1 for r in test_rules if kb.lookup_rule(r) is not None)
    success_rate = success_count / len(test_rules)
    assert success_rate >= 0.90, f"Rule lookup success rate {success_rate:.2%} < 90%"


def test_semantic_query_retrieval():
    """Verify relevant search queries return expected documents in top 3."""
    kb = KnowledgeBase()

    # Query 1: SQL injection
    results = kb.search("sql injection string formatting f-string", top_k=3)
    assert len(results) > 0
    top_chunk, score = results[0]
    assert "injection" in top_chunk.doc_path.lower() or top_chunk.rule_id == "SEC-SQLI-001"

    # Query 2: Hardcoded secrets
    results = kb.search("aws access key secret leaked token", top_k=3)
    assert len(results) > 0
    found_secrets = any("secret" in chunk.doc_path.lower() for chunk, _ in results)
    assert found_secrets

    # Query 3: Cyclomatic complexity
    results = kb.search("cyclomatic complexity deep nesting function length", top_k=3)
    assert len(results) > 0
    found_style = any(
        "style" in chunk.doc_path.lower() or "readability" in chunk.doc_path.lower()
        for chunk, _ in results
    )
    assert found_style

    # Query 4: Subprocess shell true
    results = kb.search("subprocess shell command injection", top_k=3)
    assert len(results) > 0
    found_cmd = any(
        "SEC-CMDI-001" == chunk.rule_id or "injection" in chunk.doc_path for chunk, _ in results
    )
    assert found_cmd


def test_retrieval_plugin_functions():
    """Verify Semantic Kernel plugin methods return valid JSON responses."""
    plugin = RetrievalPlugin()

    # Search function
    res_json = plugin.search_knowledge_base(
        "SQL injection parameterized query", category_filter="security"
    )
    data = json.loads(res_json)
    assert data["status"] == "ok"
    assert len(data["matches"]) > 0
    assert "citation" in data["matches"][0]

    # Direct lookup function
    res_json = plugin.lookup_rule_citation("SEC-SQLI-001")
    data = json.loads(res_json)
    assert data["status"] == "ok"
    assert data["rule_id"] == "SEC-SQLI-001"
    assert "injection_and_unsafe_apis.md#SEC-SQLI-001" in data["citation"]
