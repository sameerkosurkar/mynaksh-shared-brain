"""HTTP providers for OpenAI(-compatible), Anthropic and Gemini.

Plain httpx calls instead of vendor SDKs: fewer dependencies, identical error handling, and
adding a provider is ~30 lines.
"""
from __future__ import annotations

import time

import httpx

from app.llm.base import LLMError, LLMProvider, LLMRequest, LLMResponse


def _post(url: str, *, headers: dict, payload: dict, timeout: float) -> dict:
    try:
        resp = httpx.post(url, headers=headers, json=payload, timeout=timeout)
    except httpx.TimeoutException as exc:
        raise LLMError(f"timeout: {exc}") from exc
    except httpx.HTTPError as exc:
        raise LLMError(f"transport error: {exc}") from exc
    if resp.status_code >= 400:
        retryable = resp.status_code == 429 or resp.status_code >= 500
        raise LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}", retryable=retryable,
                       retry_after=_retry_after(resp))
    return resp.json()


def _retry_after(resp: httpx.Response) -> float | None:
    """Seconds to wait from the Retry-After header (rate limits); None if absent or not numeric."""
    try:
        return float(resp.headers["retry-after"])
    except (KeyError, ValueError):
        return None


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str, base_url: str, timeout: float):
        if not api_key:
            raise LLMError("OPENAI_API_KEY is not set", retryable=False)
        self.api_key, self.model, self.base_url, self.timeout = api_key, model, base_url.rstrip("/"), timeout

    def generate(self, request: LLMRequest) -> LLMResponse:
        start = time.monotonic()
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": request.system}]
            + [{"role": m.role, "content": m.content} for m in request.messages],
            "max_completion_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if request.json_mode:
            payload["response_format"] = {"type": "json_object"}
        data = _post(f"{self.base_url}/chat/completions", payload=payload, timeout=self.timeout,
                     headers={"Authorization": f"Bearer {self.api_key}"})
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as exc:
            raise LLMError(f"unexpected response shape: {data}") from exc
        return LLMResponse(text.strip(), self.name, self.model, int((time.monotonic() - start) * 1000))


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str, timeout: float):
        if not api_key:
            raise LLMError("ANTHROPIC_API_KEY is not set", retryable=False)
        self.api_key, self.model, self.timeout = api_key, model, timeout

    def generate(self, request: LLMRequest) -> LLMResponse:
        start = time.monotonic()
        system = request.system + ("\nRespond with valid JSON only." if request.json_mode else "")
        payload = {
            "model": self.model,
            "system": system,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        data = _post("https://api.anthropic.com/v1/messages", payload=payload, timeout=self.timeout,
                     headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"})
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        if not text:
            raise LLMError(f"empty response: {str(data)[:300]}")
        return LLMResponse(text.strip(), self.name, self.model, int((time.monotonic() - start) * 1000))


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str, timeout: float):
        if not api_key:
            raise LLMError("GEMINI_API_KEY is not set", retryable=False)
        self.api_key, self.model, self.timeout = api_key, model, timeout

    def generate(self, request: LLMRequest) -> LLMResponse:
        start = time.monotonic()
        config: dict = {
            "temperature": request.temperature,
            # Newer Gemini models count "thinking" tokens against this limit, so leave headroom.
            "maxOutputTokens": max(request.max_tokens * 3, 2048),
        }
        if request.json_mode:
            config["responseMimeType"] = "application/json"
        payload = {
            "systemInstruction": {"parts": [{"text": request.system}]},
            "contents": [{"role": "model" if m.role == "assistant" else "user", "parts": [{"text": m.content}]}
                         for m in request.messages],
            "generationConfig": config,
        }
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        data = _post(url, payload=payload, timeout=self.timeout, headers={"x-goog-api-key": self.api_key})
        try:
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        except (KeyError, IndexError) as exc:
            raise LLMError(f"unexpected response shape: {str(data)[:300]}") from exc
        if not text:
            raise LLMError("empty response from Gemini")
        return LLMResponse(text.strip(), self.name, self.model, int((time.monotonic() - start) * 1000))
