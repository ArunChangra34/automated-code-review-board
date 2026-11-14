"""Factory for Semantic Kernel instance and AI chat completion services."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from semantic_kernel.connectors.ai.prompt_execution_settings import PromptExecutionSettings
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.streaming_chat_message_content import StreamingChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from config.settings import Settings, get_settings
from core.logging_setup import get_logger

logger = get_logger("kernel_factory")


class OfflineStubChatCompletion(ChatCompletionClientBase):
    """Deterministic local stub chat completion service for offline execution mode."""

    service_id: str = "offline_stub"
    ai_model_id: str = "offline-stub-model"

    async def get_chat_message_contents(
        self,
        chat_history: ChatHistory,
        settings: PromptExecutionSettings,
        **kwargs: Any,
    ) -> list[ChatMessageContent]:
        """Return a structured empty finding list indicating offline execution."""
        return [
            ChatMessageContent(
                role=AuthorRole.ASSISTANT,
                content='{"status": "offline_mode", "additional_findings": []}',
            )
        ]

    async def get_streaming_chat_message_contents(
        self,
        chat_history: ChatHistory,
        settings: PromptExecutionSettings,
        **kwargs: Any,
    ) -> AsyncGenerator[list[StreamingChatMessageContent], Any]:
        """Streaming dummy yield for interface compliance."""
        yield [
            StreamingChatMessageContent(
                role=AuthorRole.ASSISTANT,
                content="",
                choice_index=0,
            )
        ]


def create_kernel(settings: Settings | None = None) -> Kernel:
    """Create and configure a Semantic Kernel instance with the appropriate chat completion service."""
    app_settings = settings or get_settings()
    kernel = Kernel()

    if app_settings.mode == "llm" and app_settings.llm_api_key:
        try:
            service: ChatCompletionClientBase
            if app_settings.llm_provider.lower() == "azure_openai" and app_settings.llm_endpoint:
                from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion

                service = AzureChatCompletion(
                    service_id="chat_completion",
                    deployment_name=app_settings.llm_model_id,
                    api_key=app_settings.llm_api_key,
                    endpoint=app_settings.llm_endpoint,
                )
            else:
                from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion

                service = OpenAIChatCompletion(
                    service_id="chat_completion",
                    ai_model_id=app_settings.llm_model_id,
                    api_key=app_settings.llm_api_key,
                )
            kernel.add_service(service)
            logger.info(
                "Semantic Kernel initialized with model service: %s", app_settings.llm_model_id
            )
            return kernel
        except Exception as err:
            logger.warning(
                "Failed to initialize LLM chat service (%s). Falling back to offline stub.",
                err,
            )

    # Offline mode or missing API key fallback
    stub_service = OfflineStubChatCompletion()
    kernel.add_service(stub_service)
    logger.debug("Semantic Kernel initialized with OfflineStubChatCompletion service.")
    return kernel
