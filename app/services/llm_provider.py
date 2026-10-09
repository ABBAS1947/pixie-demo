"""Abstract LLM provider interface.

Pixie can use different models for different tasks (chat vs extraction vs
summarization).  This module defines the contract that all providers must
satisfy so callers never depend on a specific backend.
"""
from abc import ABC, abstractmethod
from typing import AsyncIterator


class LLMProvider(ABC):
    """Abstract interface for LLM providers."""

    @abstractmethod
    async def complete(
        self,
        messages: list[dict],
        *,
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> dict:
        """Single (non-streaming) completion.

        Returns a dict with:
          - ``content``: the text response (str, may be empty)
          - ``tool_calls``: list of ``{id, name, arguments}`` dicts (only when tools are used)
        """
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[dict],
        *,
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator:
        """Streaming completion.

        Yields items in the same format the existing ``DeepSeekProvider.stream``
        uses so callers don't need to change:

        * **without tools** → plain ``str`` chunks
        * **with tools** → ``{"text": "..."}`` dicts for content/reasoning,
          ``{"tool_calls": [...]}`` dict at the end if the model called tools.
        """
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name of the model backing this provider."""
        ...
