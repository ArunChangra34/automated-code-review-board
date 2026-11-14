"""Base agent abstraction integrating Semantic Kernel ChatCompletionAgent."""

from __future__ import annotations

import asyncio
import json
import time
from abc import ABC, abstractmethod
from typing import Any, Literal

from semantic_kernel import Kernel
from semantic_kernel.agents import ChatCompletionAgent

from config.settings import Settings, get_settings
from core.logging_setup import get_logger
from core.models import AgentResult, Category, Finding, Severity
from core.state import ChangeState


class BaseAgent(ABC):
    """Abstract base class for all specialist review agents and the manager."""

    def __init__(
        self,
        name: str,
        description: str,
        instructions: str,
        category: Category,
        kernel: Kernel,
        plugins: list[Any] | None = None,
        settings: Settings | None = None,
    ):
        self.name = name
        self.description = description
        self.instructions = instructions
        self.category = category
        self.kernel = kernel
        self.settings = settings or get_settings()
        self.logger = get_logger(f"agent.{name}")
        self.mode: Literal["offline", "llm"] = self.settings.mode
        self.timeout_seconds: float = self.settings.agent_timeout_seconds

        # Register plugins with Kernel if provided
        self.plugins = plugins or []
        for plugin in self.plugins:
            plugin_name = getattr(plugin, "name", plugin.__class__.__name__)
            # Kernel add_plugin if not already added
            if plugin_name not in self.kernel.plugins:
                self.kernel.add_plugin(plugin, plugin_name=plugin_name)

        # Build Semantic Kernel ChatCompletionAgent
        self.sk_agent = ChatCompletionAgent(
            kernel=self.kernel,
            name=self.name,
            description=self.description,
            instructions=self.instructions,
        )

    @abstractmethod
    async def analyze_deterministic(self, state: ChangeState) -> list[Finding]:
        """Execute deterministic, offline analysis using local plugins and heuristics."""
        raise NotImplementedError

    async def run(self, state: ChangeState) -> AgentResult:
        """Execute the agent pipeline with timeout protection, error isolation, and LLM augmentation."""
        start_time = time.perf_counter()
        self.logger.info("Starting execution for change %s", state.change_id)
        await state.record_agent_start(self.name)

        # Check for simulated failure configuration
        if (
            self.settings.simulate_failure
            and self.settings.simulate_failure.lower() == self.name.lower()
        ):
            duration_ms = (time.perf_counter() - start_time) * 1000
            err_msg = f"Simulated fault injection failure triggered for {self.name}"
            self.logger.error(err_msg)
            result = AgentResult(
                agent_name=self.name,
                status="failed",
                findings=[],
                duration_ms=round(duration_ms, 2),
                error=err_msg,
                mode=self.mode,
            )
            await state.record_agent_result(result)
            return result

        try:
            # Wrap execution with strict timeout
            result = await asyncio.wait_for(
                self._execute_pipeline(state, start_time),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            duration_ms = (time.perf_counter() - start_time) * 1000
            err_msg = f"Agent execution exceeded timeout limit of {self.timeout_seconds}s"
            self.logger.warning(err_msg)
            result = AgentResult(
                agent_name=self.name,
                status="timeout",
                findings=[],
                duration_ms=round(duration_ms, 2),
                error=err_msg,
                mode=self.mode,
            )
        except Exception as err:
            duration_ms = (time.perf_counter() - start_time) * 1000
            err_msg = f"Unhandled error in agent {self.name}: {err}"
            self.logger.exception(err_msg)
            result = AgentResult(
                agent_name=self.name,
                status="failed",
                findings=[],
                duration_ms=round(duration_ms, 2),
                error=err_msg,
                mode=self.mode,
            )

        await state.record_agent_result(result)
        return result

    async def _execute_pipeline(self, state: ChangeState, start_time: float) -> AgentResult:
        """Internal execution pipeline running deterministic analysis and optional LLM augmentation."""
        findings: list[Finding] = []
        status: Literal["ok", "degraded", "failed", "timeout"] = "ok"
        error_msg: str | None = None

        # Step 1: Deterministic offline analysis (always runs)
        try:
            findings = await self.analyze_deterministic(state)
        except Exception as err:
            self.logger.exception("Error in deterministic analysis: %s", err)
            duration_ms = (time.perf_counter() - start_time) * 1000
            return AgentResult(
                agent_name=self.name,
                status="failed",
                findings=[],
                duration_ms=round(duration_ms, 2),
                error=f"Deterministic analysis failed: {err}",
                mode=self.mode,
            )

        # Step 2: LLM augmentation (if configured and in llm mode)
        if self.mode == "llm" and self.settings.llm_api_key:
            try:
                augmented_findings = await self._augment_with_llm(state, findings)
                findings = augmented_findings
            except Exception as err:
                self.logger.warning(
                    "LLM augmentation failed (%s); degrading gracefully to offline findings", err
                )
                status = "degraded"
                error_msg = f"LLM augmentation failed: {err}"

        duration_ms = (time.perf_counter() - start_time) * 1000
        return AgentResult(
            agent_name=self.name,
            status=status,
            findings=findings,
            duration_ms=round(duration_ms, 2),
            error=error_msg,
            mode=self.mode,
        )

    async def _augment_with_llm(
        self, state: ChangeState, existing_findings: list[Finding]
    ) -> list[Finding]:
        """Invoke Semantic Kernel agent to semantically analyze diff and return validated findings."""
        # Formulate token-optimized prompt containing compact diff and existing findings summary
        diff_snippet = state.raw_diff[:4000]  # Cap diff to prevent context bloat
        findings_summary = [
            {
                "id": f.id,
                "rule": f.rule_id,
                "title": f.title,
                "file": f.file_path,
                "line": f.line_start,
            }
            for f in existing_findings
        ]

        prompt = (
            f"Review the following diff as {self.name} ({self.category.value}).\n"
            f"Existing deterministic findings: {json.dumps(findings_summary)}\n\n"
            f"Diff:\n{diff_snippet}\n\n"
            "Return a JSON array of findings adhering to the Finding schema. "
            "Output strictly valid JSON with no markdown wrapping or extra prose."
        )

        # Attempt invocation with one retry for JSON validation
        for attempt in range(2):
            response_text = ""
            async for msg in self.sk_agent.invoke(messages=prompt):
                if msg.content:
                    response_text += str(msg.content)

            # Strip markdown formatting if present
            cleaned = response_text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            try:
                parsed = json.loads(cleaned)
                new_findings = list(existing_findings)
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, dict):
                            # Validate schema
                            finding = Finding(
                                id=item.get("id")
                                or Finding.generate_id(
                                    self.category,
                                    item.get("rule_id", "SEM-LLM-001"),
                                    item.get("file_path"),
                                    item.get("line_start"),
                                ),
                                category=self.category,
                                severity=Severity(item.get("severity", "LOW")),
                                title=item.get("title", "Semantic finding"),
                                description=item.get("description", ""),
                                file_path=item.get("file_path"),
                                line_start=item.get("line_start"),
                                line_end=item.get("line_end"),
                                code_snippet=item.get("code_snippet"),
                                rule_id=item.get("rule_id", "SEM-LLM-001"),
                                evidence_source=item.get("evidence_source"),
                                recommendation=item.get("recommendation", "Review code"),
                                confidence=float(item.get("confidence", 0.85)),
                                reported_by=[self.name],
                            )
                            new_findings.append(finding)
                return new_findings
            except Exception as parse_err:
                if attempt == 0:
                    prompt = (
                        f"Previous output failed JSON parsing: {parse_err}. "
                        "Please output ONLY a valid JSON list of finding objects."
                    )
                    continue
                raise ValueError(f"Failed to parse valid JSON from LLM: {parse_err}") from parse_err

        return existing_findings
