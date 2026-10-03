"""Provider-agnostic LLM interface. The rest of the app only depends on this module."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class ChatMessage:
    role: Literal["user", "assistant"]
    content: str


@dataclass
class LLMRequest:
    system: str
    messages: list[ChatMessage]
    max_tokens: int = 700
    temperature: float = 0.6
    json_mode: bool = False
    # Structured view of the same context. Real providers ignore it; the mock provider uses it to
    # produce deterministic, context-aware answers without an API key.
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    latency_ms: int = 0


class LLMError(Exception):
    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


class LLMProvider(ABC):
    name: str = "base"
    model: str = ""

    @abstractmethod
    def generate(self, request: LLMRequest) -> LLMResponse:
        """Return a completion or raise LLMError."""
