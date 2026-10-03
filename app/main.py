"""FastAPI entrypoint and dependency wiring."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.brain.store import InMemoryGraphStore, ResilientGraphStore
from app.chat.context_selector import ContextSelector
from app.chat.service import ChatService
from app.config import Settings, get_settings
from app.llm.fallback import FallbackLLM, build_llm
from app.memory.short_term import ShortTermMemory

log = logging.getLogger("app")


@dataclass
class Container:
    settings: Settings
    store: Any
    llm: FallbackLLM
    chat_service: ChatService


def build_store(settings: Settings):
    if settings.graph_backend == "memory":
        return InMemoryGraphStore()
    from app.brain.neo4j_store import Neo4jGraphStore

    primary = Neo4jGraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password,
                              settings.neo4j_database)
    store = ResilientGraphStore(primary, InMemoryGraphStore(), settings.graph_circuit_cooldown_seconds)
    if store.ping():
        log.info("connected to Neo4j at %s", settings.neo4j_uri)
    else:
        log.error("Neo4j at %s unreachable - running on in-memory fallback until it recovers", settings.neo4j_uri)
    return store


def build_container(settings: Settings, store: Any = None, llm: Optional[FallbackLLM] = None,
                    today=None) -> Container:
    store = store if store is not None else build_store(settings)
    llm = llm or build_llm(settings)
    kwargs = {"today": today} if today else {}
    service = ChatService(
        store=store, llm=llm,
        short_term=ShortTermMemory(settings.short_term_turns, settings.session_ttl_seconds),
        selector=ContextSelector(settings.max_context_items, settings.max_context_tokens, settings.short_term_turns),
        extraction_mode=settings.extraction_mode, min_confidence=settings.min_memory_confidence, **kwargs)
    return Container(settings, store, llm, service)


def create_app(container: Optional[Container] = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if getattr(app.state, "container", None) is None:
            settings = get_settings()
            logging.basicConfig(level=settings.log_level,
                                format="%(asctime)s %(levelname)s %(name)s - %(message)s")
            app.state.container = build_container(settings)
            log.info("LLM chain: %s", [p.name for p in app.state.container.llm.providers])
        yield
        app.state.container.store.close()

    app = FastAPI(title="MyNaksh Shared Brain Chat", version="1.0.0", lifespan=lifespan,
                  description="Personalised astrology chat with short-term context and a graph-based Shared Brain.")
    app.state.container = container
    app.include_router(router)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError):
        errors = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
        return JSONResponse(status_code=422, content={"error": "invalid_input", "details": errors})

    @app.exception_handler(Exception)
    async def unhandled_handler(_: Request, exc: Exception):
        log.exception("unhandled error: %s", exc)
        return JSONResponse(status_code=500, content={"error": "internal_error",
                                                      "message": "Something went wrong. Please try again."})

    return app


app = create_app()
