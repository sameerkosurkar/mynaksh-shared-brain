from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from app.api.schemas import ChatRequest, ChatResponse, ProfileIn, UserCreate, UserOut
from app.brain.models import PROFILE_FIELDS
from app.memory.extractor import Candidate, Extraction
from app.profile.astrology import astro_profile, missing_profile_fields

router = APIRouter()


def _services(request: Request):
    return request.app.state.container


def _user_out(user: dict) -> UserOut:
    astro = astro_profile(user)
    return UserOut(**{k: user.get(k) for k in ("user_id", *PROFILE_FIELDS)}, sun_sign=astro.get("sun_sign"),
                   astrology=astro, missing_profile_fields=missing_profile_fields(user))


def _save_profile(c, user_id: str, body: ProfileIn) -> dict:
    """Profile writes go through the same updater as chat so history/zodiac logic is shared."""
    data = body.model_dump(exclude_none=True)
    if "date_of_birth" in data:
        data["date_of_birth"] = data["date_of_birth"].isoformat()
    if c.store.get_user(user_id) is None:
        c.store.upsert_user(user_id, {})
    ex = Extraction(profile={k: str(v) for k, v in data.items()})
    if "preferred_language" in data:
        ex.items.append(Candidate("preference", "preference:language", data["preferred_language"].capitalize(),
                                  "personal", {"type": "language"}, 0.95, 0.7, "profile api"))
    c.chat_service.updater.apply(user_id, ex)
    return c.store.get_user(user_id)


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED, tags=["profile"])
def create_user(body: UserCreate, request: Request):
    """Create a user (optionally with profile). Idempotent: re-posting updates the profile."""
    c = _services(request)
    user = _save_profile(c, body.user_id, ProfileIn(**body.model_dump(exclude={"user_id"})))
    return _user_out(user)


@router.patch("/users/{user_id}/profile", response_model=UserOut, tags=["profile"])
def update_profile(user_id: str, body: ProfileIn, request: Request):
    c = _services(request)
    if c.store.get_user(user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"user '{user_id}' not found")
    return _user_out(_save_profile(c, user_id, body))


@router.get("/users/{user_id}", response_model=UserOut, tags=["profile"])
def get_user(user_id: str, request: Request):
    user = _services(request).store.get_user(user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"user '{user_id}' not found")
    return _user_out(user)


@router.get("/users/{user_id}/brain", tags=["shared brain"])
def get_brain(user_id: str, request: Request):
    """Inspect the user's sub-graph in the Shared Brain (debug / transparency)."""
    brain = _services(request).store.get_brain(user_id)
    if brain is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"user '{user_id}' not found")
    return brain


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["shared brain"])
def delete_user(user_id: str, request: Request):
    """Right to be forgotten: removes the user and all their memories."""
    if not _services(request).store.delete_user(user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"user '{user_id}' not found")


@router.post("/chat", response_model=ChatResponse, tags=["chat"])
def chat(body: ChatRequest, request: Request):
    result = _services(request).chat_service.chat(body.user_id, body.session_id, body.message)
    return ChatResponse(user_id=body.user_id, session_id=body.session_id, **result.__dict__)


@router.get("/health", tags=["ops"])
def health(request: Request):
    c = _services(request)
    graph_ok = c.store.ping()
    return {
        "status": "ok" if graph_ok else "degraded",
        "graph_backend": c.settings.graph_backend,
        "graph_available": graph_ok,
        "llm_provider": c.llm.primary.name,
        "llm_model": c.llm.primary.model,
        "llm_chain": [p.name for p in c.llm.providers],
    }
