"""Application settings, loaded from environment variables / `.env`."""
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- LLM ---------------------------------------------------------------
    llm_provider: Literal["mock", "openai", "anthropic", "gemini"] = "mock"
    llm_timeout_seconds: float = 20.0
    llm_max_retries: int = 1
    # If the primary provider fails, fall back to the deterministic mock instead of erroring.
    llm_fallback_to_mock: bool = True

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    # Any OpenAI-compatible endpoint works (Azure, Groq, Ollama, vLLM ...).
    openai_base_url: str = "https://api.openai.com/v1"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"

    # --- Shared Brain (graph) ---------------------------------------------
    graph_backend: Literal["neo4j", "memory"] = "neo4j"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "mynaksh-dev-password"
    neo4j_database: str = "neo4j"
    graph_circuit_cooldown_seconds: float = 30.0

    # --- Memory / context --------------------------------------------------
    # "rules" = deterministic extractor only; "hybrid" = rules + LLM extractor (needs a real LLM).
    extraction_mode: Literal["rules", "hybrid"] = "hybrid"
    short_term_turns: int = 6           # user+assistant messages kept verbatim per session
    session_ttl_seconds: int = 6 * 3600
    max_context_items: int = 8          # long-term memories sent to the LLM per turn
    max_context_tokens: int = 1200      # rough budget for the injected user context
    min_memory_confidence: float = 0.5  # candidates below this are not persisted

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
