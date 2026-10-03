"""Provider chain with retries: primary -> (optional) mock fallback."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from app.config import Settings
from app.llm.base import LLMError, LLMProvider, LLMRequest, LLMResponse
from app.llm.mock import MockProvider
from app.llm.providers import AnthropicProvider, GeminiProvider, OpenAIProvider

log = logging.getLogger(__name__)


@dataclass
class LLMResult:
    response: LLMResponse
    degraded: bool          # True if the configured primary provider did not answer


class FallbackLLM:
    def __init__(self, providers: list[LLMProvider], max_retries: int = 1):
        if not providers:
            raise ValueError("at least one provider required")
        self.providers = providers
        self.max_retries = max_retries

    @property
    def primary(self) -> LLMProvider:
        return self.providers[0]

    @property
    def is_real(self) -> bool:
        return self.primary.name != "mock"

    def generate(self, request: LLMRequest) -> LLMResult:
        errors = []
        for idx, provider in enumerate(self.providers):
            for attempt in range(self.max_retries + 1):
                try:
                    resp = provider.generate(request)
                    return LLMResult(resp, degraded=idx > 0)
                except LLMError as exc:
                    errors.append(f"{provider.name}: {exc}")
                    log.warning("LLM %s attempt %d failed: %s", provider.name, attempt + 1, exc)
                    if not exc.retryable:
                        break
                    time.sleep(min(0.5 * (2 ** attempt), 2.0))
                except Exception as exc:  # noqa: BLE001 - never let a provider bug escape
                    errors.append(f"{provider.name}: {exc!r}")
                    log.exception("LLM %s crashed", provider.name)
                    break
        raise LLMError("all providers failed: " + " | ".join(errors), retryable=False)


def build_llm(settings: Settings) -> FallbackLLM:
    providers: list[LLMProvider] = []
    try:
        if settings.llm_provider == "openai":
            providers.append(OpenAIProvider(settings.openai_api_key, settings.openai_model,
                                            settings.openai_base_url, settings.llm_timeout_seconds))
        elif settings.llm_provider == "anthropic":
            providers.append(AnthropicProvider(settings.anthropic_api_key, settings.anthropic_model,
                                               settings.llm_timeout_seconds))
        elif settings.llm_provider == "gemini":
            providers.append(GeminiProvider(settings.gemini_api_key, settings.gemini_model,
                                            settings.llm_timeout_seconds))
    except LLMError as exc:
        log.error("LLM provider %s not usable (%s); falling back to mock", settings.llm_provider, exc)
    if not providers or settings.llm_fallback_to_mock:
        providers.append(MockProvider())
    return FallbackLLM(providers, settings.llm_max_retries)
