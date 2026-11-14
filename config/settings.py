"""Application settings and configuration management."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global configuration settings for Automated Code Review Board."""

    model_config = SettingsConfigDict(
        env_prefix="CRB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Execution Mode: offline (deterministic, no API key) or llm (Semantic Kernel model augmented)
    mode: Literal["offline", "llm"] = Field(
        default="offline",
        description="Execution mode: 'offline' (rule-based tools only) or 'llm' (model-augmented)",
    )

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")

    # Agent Execution & Timeouts
    agent_timeout_seconds: float = Field(
        default=60.0,
        description="Maximum execution time allowed per agent in seconds",
    )
    simulate_failure: str | None = Field(
        default=None,
        description="Optional agent name to simulate failure for testing resilience",
    )

    # Model Service Configuration (Semantic Kernel)
    llm_provider: str = Field(
        default="openai", description="Model provider (e.g. openai, azure_openai)"
    )
    llm_model_id: str = Field(default="gpt-4o", description="Model identifier")
    llm_api_key: str | None = Field(default=None, description="API key for model service")
    llm_endpoint: str | None = Field(default=None, description="Optional custom endpoint URL")

    # Analysis Thresholds
    severity_policy_path: str = Field(
        default="config/severity_policy.yaml",
        description="Path to YAML file defining severity policy and merge thresholds",
    )
    entropy_threshold: float = Field(
        default=4.3,
        description="Shannon entropy threshold for secret detection",
    )
    max_line_length: int = Field(default=100, description="Max allowed line length for style check")
    max_function_lines: int = Field(default=60, description="Max allowed function length in lines")
    max_cyclomatic_complexity: int = Field(default=10, description="Max cyclomatic complexity")

    def load_severity_policy(self) -> dict[str, Any]:
        """Load and parse the YAML severity policy."""
        policy_path = Path(self.severity_policy_path)
        if not policy_path.is_absolute():
            # Resolve relative to current working directory or file directory
            if not policy_path.exists():
                policy_path = Path(__file__).resolve().parent / "severity_policy.yaml"

        if not policy_path.exists():
            # Fallback default policy if file not found
            return {
                "weights": {"CRITICAL": 40, "HIGH": 20, "MEDIUM": 8, "LOW": 2, "INFO": 0},
                "blocking_severities": ["CRITICAL", "HIGH"],
                "thresholds": {
                    "request_changes_score": 30,
                    "max_score": 100,
                    "corroboration_multiplier": 0.10,
                },
                "category_priority": ["security", "test_coverage", "style", "diff"],
                "size_thresholds": {"XS": 20, "S": 100, "M": 300, "L": 800, "XL": 99999999},
            }

        with open(policy_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached singleton settings instance."""
    return Settings()
