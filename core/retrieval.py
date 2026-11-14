"""Offline grounded retrieval engine indexing local knowledge base documents."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass
class KnowledgeChunk:
    """An indexed section from the engineering knowledge base."""

    chunk_id: str
    doc_path: str
    section: str
    rule_id: str | None
    citation: str
    content: str
    category: str


class KnowledgeBase:
    """TF-IDF indexed knowledge base for offline semantic retrieval and grounding."""

    def __init__(self, root_dir: str | Path = "knowledge_base"):
        self.root_dir = Path(root_dir)
        self.chunks: list[KnowledgeChunk] = []
        self.rule_index: dict[str, KnowledgeChunk] = {}
        self.vectorizer: TfidfVectorizer | None = None
        self.tfidf_matrix = None
        self._load_and_index()

    def _extract_rule_id(self, text: str) -> str | None:
        """Extract canonical rule ID or recipe identifier."""
        # Check for recipe format first e.g. RECIPE-SEC-SQLI-001
        recipe_match = re.search(r"\b(RECIPE-[A-Z0-9-]+)\b", text)
        if recipe_match:
            return recipe_match.group(1)
        # Check for standard rule code e.g. SEC-SQLI-001, STY-NAME-001, TST-UNTESTED-001
        match = re.search(r"\b([A-Z]{3,5}-[A-Z0-9]+-\d{3})\b", text)
        if match:
            return match.group(1)
        return None

    def _load_and_index(self) -> None:
        """Parse all markdown files under root_dir into heading-based chunks."""
        if not self.root_dir.exists():
            return

        md_files = sorted(self.root_dir.rglob("*.md"))
        heading_re = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)

        for file_path in md_files:
            rel_path = file_path.relative_to(self.root_dir).as_posix()
            category = rel_path.split("/")[0] if "/" in rel_path else "general"

            text = file_path.read_text(encoding="utf-8")
            matches = list(heading_re.finditer(text))

            if not matches:
                # Whole document as single chunk
                rule_id = self._extract_rule_id(text)
                citation = f"{rel_path}#overview"
                chunk = KnowledgeChunk(
                    chunk_id=f"{rel_path}:0",
                    doc_path=rel_path,
                    section="Overview",
                    rule_id=rule_id,
                    citation=citation,
                    content=text.strip(),
                    category=category,
                )
                self.chunks.append(chunk)
                if rule_id:
                    # Do not let recipe files overwrite canonical rule definitions
                    if rule_id not in self.rule_index or not rule_id.startswith("RECIPE-"):
                        self.rule_index[rule_id] = chunk
                continue

            for idx, match in enumerate(matches):
                heading_title = match.group(2).strip()
                start_pos = match.end()
                end_pos = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
                section_body = text[start_pos:end_pos].strip()

                full_chunk_text = f"{heading_title}\n{section_body}".strip()
                rule_id = self._extract_rule_id(heading_title) or self._extract_rule_id(
                    section_body
                )

                # Generate clean anchor
                anchor = rule_id or re.sub(r"[^a-zA-Z0-9_-]+", "-", heading_title).lower().strip(
                    "-"
                )
                citation = f"{rel_path}#{anchor}"

                chunk = KnowledgeChunk(
                    chunk_id=f"{rel_path}:{idx}",
                    doc_path=rel_path,
                    section=heading_title,
                    rule_id=rule_id,
                    citation=citation,
                    content=full_chunk_text,
                    category=category,
                )
                self.chunks.append(chunk)
                if rule_id:
                    # Do not let recipe files overwrite canonical rule definitions
                    if rule_id not in self.rule_index or not rule_id.startswith("RECIPE-"):
                        self.rule_index[rule_id] = chunk

        # Build TF-IDF vector space with optimized token pattern preserving hyphens
        if self.chunks:
            corpus = [f"{c.section} {c.content}" for c in self.chunks]
            self.vectorizer = TfidfVectorizer(
                token_pattern=r"(?u)\b[\w-]+\b",
                ngram_range=(1, 2),
                sublinear_tf=True,
                stop_words="english",
            )
            self.tfidf_matrix = self.vectorizer.fit_transform(corpus)

    def lookup_rule(self, rule_id: str) -> KnowledgeChunk | None:
        """Fast direct retrieval of a rule chunk by its rule identifier."""
        return self.rule_index.get(rule_id)

    def search(
        self,
        query: str,
        top_k: int = 3,
        category_filter: str | None = None,
    ) -> list[tuple[KnowledgeChunk, float]]:
        """Search the knowledge base using TF-IDF cosine similarity."""
        if not self.chunks or self.vectorizer is None or self.tfidf_matrix is None:
            return []

        # Check if query matches a known rule ID exactly
        exact_rule = self._extract_rule_id(query)
        if exact_rule and exact_rule in self.rule_index:
            chunk = self.rule_index[exact_rule]
            if not category_filter or chunk.category == category_filter:
                return [(chunk, 1.0)]

        query_vec = self.vectorizer.transform([query])
        scores = cosine_similarity(query_vec, self.tfidf_matrix).flatten()

        results: list[tuple[KnowledgeChunk, float]] = []
        for idx in scores.argsort()[::-1]:
            score = float(scores[idx])
            if score <= 0.0:
                break
            chunk = self.chunks[idx]
            if category_filter and chunk.category != category_filter:
                continue
            results.append((chunk, score))
            if len(results) >= top_k:
                break

        return results


@lru_cache(maxsize=1)
def get_knowledge_base() -> KnowledgeBase:
    """Return singleton cached instance of KnowledgeBase."""
    return KnowledgeBase()
