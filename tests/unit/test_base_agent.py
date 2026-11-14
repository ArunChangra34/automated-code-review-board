"""Unit tests for KernelFactory and BaseAgent lifecycle."""

import asyncio

import pytest

from agents.base_agent import BaseAgent
from config.settings import Settings
from core.kernel_factory import create_kernel
from core.models import Category, Finding, Severity
from core.state import ChangeState


class SampleConcreteAgent(BaseAgent):
    """Test concrete implementation of BaseAgent."""

    def __init__(self, kernel, settings=None, should_fail=False, sleep_duration=0.0):
        super().__init__(
            name="test_specialist",
            description="Specialist test agent for verifying base functionality",
            instructions="Analyze test changes",
            category=Category.DIFF,
            kernel=kernel,
            settings=settings,
        )
        self.should_fail = should_fail
        self.sleep_duration = sleep_duration

    async def analyze_deterministic(self, state: ChangeState) -> list[Finding]:
        if self.sleep_duration > 0:
            await asyncio.sleep(self.sleep_duration)

        if self.should_fail:
            raise RuntimeError("Deliberate test failure in analysis")

        return [
            Finding(
                id=Finding.generate_id(self.category, "DIFF-001", "file.py", 1),
                category=self.category,
                severity=Severity.INFO,
                title="Test finding",
                description="Test finding description",
                rule_id="DIFF-001",
                recommendation="Test recommendation",
                reported_by=[self.name],
            )
        ]


@pytest.mark.asyncio
async def test_base_agent_successful_run():
    """Verify normal execution returning AgentResult."""
    kernel = create_kernel()
    agent = SampleConcreteAgent(kernel=kernel)
    state = ChangeState(change_id="c1", source="test", raw_diff="diff")

    result = await agent.run(state)
    assert result.agent_name == "test_specialist"
    assert result.status == "ok"
    assert len(result.findings) == 1
    assert result.duration_ms >= 0.0
    assert result.error is None
    assert state.agent_results["test_specialist"] == result


@pytest.mark.asyncio
async def test_base_agent_handles_exception():
    """Verify forced exception is captured into AgentResult without crashing."""
    kernel = create_kernel()
    agent = SampleConcreteAgent(kernel=kernel, should_fail=True)
    state = ChangeState(change_id="c2", source="test", raw_diff="diff")

    result = await agent.run(state)
    assert result.status == "failed"
    assert "Deliberate test failure" in (result.error or "")
    assert len(result.findings) == 0


@pytest.mark.asyncio
async def test_base_agent_handles_timeout():
    """Verify forced timeout is captured into AgentResult without crashing."""
    kernel = create_kernel()
    settings = Settings(agent_timeout_seconds=0.1)
    agent = SampleConcreteAgent(kernel=kernel, settings=settings, sleep_duration=0.3)
    state = ChangeState(change_id="c3", source="test", raw_diff="diff")

    result = await agent.run(state)
    assert result.status == "timeout"
    assert "exceeded timeout limit" in (result.error or "")


@pytest.mark.asyncio
async def test_base_agent_simulated_failure_flag():
    """Verify simulate_failure setting triggers simulated failure."""
    kernel = create_kernel()
    settings = Settings(simulate_failure="test_specialist")
    agent = SampleConcreteAgent(kernel=kernel, settings=settings)
    state = ChangeState(change_id="c4", source="test", raw_diff="diff")

    result = await agent.run(state)
    assert result.status == "failed"
    assert "Simulated fault injection" in (result.error or "")
