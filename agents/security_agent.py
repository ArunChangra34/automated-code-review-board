"""Security Agent detecting vulnerabilities, secrets, and dangerous APIs."""

from __future__ import annotations

from semantic_kernel import Kernel

from agents.base_agent import BaseAgent
from config.settings import Settings
from core.models import Category, Finding
from core.state import ChangeState
from plugins.security_plugin import SecurityPlugin


class SecurityAgent(BaseAgent):
    """Specialist agent detecting secrets, injections, and insecure application patterns."""

    def __init__(
        self,
        kernel: Kernel,
        settings: Settings | None = None,
        plugin: SecurityPlugin | None = None,
    ):
        self.security_plugin = plugin or SecurityPlugin(settings=settings)
        instructions = (
            "You are the Security Analysis Agent. Scan code changes for vulnerabilities including "
            "SQL injection, command injection, hard-coded secrets, weak cryptography, and unsafe APIs. "
            "Never expose raw secret values in output findings. Redact all credentials. "
            "Ground findings with exact citations into the security knowledge base."
        )
        super().__init__(
            name="security_agent",
            description="Identifies security vulnerabilities, leaked credentials, and unsafe patterns",
            instructions=instructions,
            category=Category.SECURITY,
            kernel=kernel,
            plugins=[self.security_plugin],
            settings=settings,
        )

    async def analyze_deterministic(self, state: ChangeState) -> list[Finding]:
        """Execute deterministic vulnerability analysis and secret scanning."""
        results = self.security_plugin.check_security(state.files, risk_areas=state.risk_areas)
        return list(results)
