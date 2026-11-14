"""Style Agent evaluating formatting, readability, naming conventions, and code hygiene."""

from __future__ import annotations

from semantic_kernel import Kernel

from agents.base_agent import BaseAgent
from config.settings import Settings
from core.models import Category, Finding
from core.state import ChangeState
from plugins.style_plugin import StylePlugin


class StyleAgent(BaseAgent):
    """Specialist agent detecting code style deviations, dead code, and maintainability concerns."""

    def __init__(
        self,
        kernel: Kernel,
        settings: Settings | None = None,
        plugin: StylePlugin | None = None,
    ):
        self.style_plugin = plugin or StylePlugin(settings=settings)
        instructions = (
            "You are the Style and Code Quality Agent. Inspect changed code lines for formatting, "
            "readability, naming standards, cyclomatic complexity, and documentation completeness. "
            "Ground every finding in a specific rule from the knowledge base where applicable."
        )
        super().__init__(
            name="style_agent",
            description="Inspects added code for style, conventions, complexity, and docstring coverage",
            instructions=instructions,
            category=Category.STYLE,
            kernel=kernel,
            plugins=[self.style_plugin],
            settings=settings,
        )

    async def analyze_deterministic(self, state: ChangeState) -> list[Finding]:
        """Execute deterministic style checks on added lines across changed files."""
        results = self.style_plugin.check_style(state.files)
        return list(results)
