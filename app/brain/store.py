"""Shared Brain storage abstraction.

`GraphStore` is the contract. Two implementations:
  * `Neo4jGraphStore` (app/brain/neo4j_store.py) - the real, persistent store.
  * `InMemoryGraphStore` - same graph model held in dicts; used by tests and as a fallback.

`ResilientGraphStore` wraps a primary store with a fallback + circuit breaker so that a graph
outage degrades personalisation instead of failing the chat request.
"""
from __future__ import annotations

import copy
import logging
import threading
import time
from typing import Any, Iterable, Optional, Protocol

from app.brain.models import ACTIVE, KIND_SCHEMA, SUPERSEDED, MemoryItem, utcnow_iso

log = logging.getLogger(__name__)


class GraphStoreError(Exception):
    pass


class GraphStore(Protocol):
    def ping(self) -> bool: ...
    def get_user(self, user_id: str) -> Optional[dict]: ...
    def upsert_user(self, user_id: str, props: dict) -> dict: ...
    def set_zodiac(self, user_id: str, sign: Optional[str]) -> None: ...
    def record_profile_change(self, user_id: str, field: str, old: Any, new: Any) -> None: ...
    def upsert_item(self, user_id: str, item: MemoryItem) -> None: ...
    def find_active_item(self, user_id: str, key: str) -> Optional[MemoryItem]: ...
    def link_supersedes(self, new_id: str, old_id: str) -> None: ...
    def get_items(self, user_id: str, areas: Optional[Iterable[str]] = None,
                  kinds: Optional[Iterable[str]] = None, statuses: Iterable[str] = (ACTIVE,),
                  limit: int = 50) -> list[MemoryItem]: ...
    def record_session(self, user_id: str, session_id: str, summary: str, turns: int) -> None: ...
    def get_recent_sessions(self, user_id: str, exclude_session_id: Optional[str] = None,
                            limit: int = 2) -> list[dict]: ...
    def get_brain(self, user_id: str) -> Optional[dict]: ...
    def delete_user(self, user_id: str) -> bool: ...
    def close(self) -> None: ...


class InMemoryGraphStore:
    """Dict-backed implementation of the same graph model (nodes + typed edges)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.users: dict[str, dict] = {}
        self.zodiac: dict[str, str] = {}
        self.items: dict[str, dict[str, MemoryItem]] = {}       # user_id -> item_id -> item
        self.supersedes: list[tuple[str, str]] = []              # (new_id, old_id)
        self.profile_history: dict[str, list[dict]] = {}
        self.sessions: dict[str, dict[str, dict]] = {}

    def ping(self) -> bool:
        return True

    def get_user(self, user_id: str) -> Optional[dict]:
        with self._lock:
            u = self.users.get(user_id)
            if u is None:
                return None
            out = dict(u)
            out["sun_sign"] = self.zodiac.get(user_id)
            return out

    def upsert_user(self, user_id: str, props: dict) -> dict:
        with self._lock:
            now = utcnow_iso()
            u = self.users.setdefault(user_id, {"user_id": user_id, "created_at": now})
            u.update({k: v for k, v in props.items() if v is not None})
            u["updated_at"] = now
            return dict(u)

    def set_zodiac(self, user_id: str, sign: Optional[str]) -> None:
        with self._lock:
            if sign:
                self.zodiac[user_id] = sign
            else:
                self.zodiac.pop(user_id, None)

    def record_profile_change(self, user_id: str, field: str, old: Any, new: Any) -> None:
        with self._lock:
            self.profile_history.setdefault(user_id, []).append(
                {"field": field, "old_value": old, "new_value": new, "changed_at": utcnow_iso()})

    def upsert_item(self, user_id: str, item: MemoryItem) -> None:
        with self._lock:
            self.items.setdefault(user_id, {})[item.id] = copy.deepcopy(item)

    def find_active_item(self, user_id: str, key: str) -> Optional[MemoryItem]:
        with self._lock:
            for it in self.items.get(user_id, {}).values():
                if it.key == key and it.status == ACTIVE:
                    return copy.deepcopy(it)
            return None

    def link_supersedes(self, new_id: str, old_id: str) -> None:
        with self._lock:
            self.supersedes.append((new_id, old_id))
            for items in self.items.values():
                if old_id in items:
                    items[old_id].status = SUPERSEDED
                    items[old_id].updated_at = utcnow_iso()

    def get_items(self, user_id, areas=None, kinds=None, statuses=(ACTIVE,), limit=50):
        with self._lock:
            areas = set(areas) if areas else None
            kinds = set(kinds) if kinds else None
            statuses = set(statuses)
            out = [copy.deepcopy(it) for it in self.items.get(user_id, {}).values()
                   if it.status in statuses
                   and (areas is None or it.area in areas)
                   and (kinds is None or it.kind in kinds)]
            out.sort(key=lambda i: (i.importance, i.updated_at), reverse=True)
            return out[:limit]

    def record_session(self, user_id: str, session_id: str, summary: str, turns: int) -> None:
        with self._lock:
            now = utcnow_iso()
            s = self.sessions.setdefault(user_id, {}).setdefault(
                session_id, {"session_id": session_id, "started_at": now})
            s.update({"summary": summary, "turns": turns, "last_active": now})

    def get_recent_sessions(self, user_id, exclude_session_id=None, limit=2):
        with self._lock:
            ss = [dict(s) for sid, s in self.sessions.get(user_id, {}).items() if sid != exclude_session_id]
            ss.sort(key=lambda s: s["last_active"], reverse=True)
            return ss[:limit]

    def get_brain(self, user_id: str) -> Optional[dict]:
        with self._lock:
            user = self.get_user(user_id)
            if user is None:
                return None
            all_items = self.get_items(user_id, statuses=(ACTIVE, SUPERSEDED, "abandoned"), limit=1000)
            return _brain_view(user, self.zodiac.get(user_id), all_items, self.supersedes,
                               self.profile_history.get(user_id, []),
                               self.get_recent_sessions(user_id, limit=20))

    def delete_user(self, user_id: str) -> bool:
        with self._lock:
            existed = self.users.pop(user_id, None) is not None
            for d in (self.zodiac, self.items, self.profile_history, self.sessions):
                d.pop(user_id, None)
            return existed

    def close(self) -> None:
        pass


def _brain_view(user: dict, zodiac: Optional[str], items: list[MemoryItem],
                supersedes: Iterable[tuple[str, str]], history: list[dict], sessions: list[dict]) -> dict:
    """Shared, backend-independent JSON view of a user's sub-graph."""
    ids = {i.id for i in items}
    edges = []
    if zodiac:
        edges.append({"type": "HAS_ZODIAC", "target": {"label": "ZodiacSign", "name": zodiac}})
    for it in sorted(items, key=lambda i: (i.kind, i.created_at)):
        edges.append({
            "type": KIND_SCHEMA[it.kind][1],
            "target": {"label": KIND_SCHEMA[it.kind][0], **it.to_props()},
            "about": {"label": "LifeArea", "name": it.area},
        })
    return {
        "user": user,
        "relationships": edges,
        "supersedes": [{"new_id": n, "old_id": o} for n, o in supersedes if n in ids or o in ids],
        "profile_history": history,
        "sessions": sessions,
    }


class ResilientGraphStore:
    """Primary store with an in-memory fallback and a simple circuit breaker.

    On a primary failure we log, switch to the fallback for `cooldown` seconds, then retry the
    primary. `degraded` tells the API layer that personalisation may be incomplete.
    """

    def __init__(self, primary: Any, fallback: Optional[Any] = None, cooldown: float = 30.0):
        self.primary = primary
        self.fallback = fallback or InMemoryGraphStore()
        self.cooldown = cooldown
        self._open_until = 0.0

    @property
    def degraded(self) -> bool:
        return time.monotonic() < self._open_until

    def _call(self, name: str, *args, **kwargs):
        if not self.degraded:
            try:
                return getattr(self.primary, name)(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 - any driver error must not break chat
                log.error("graph primary failed on %s: %s - using fallback for %.0fs", name, exc, self.cooldown)
                self._open_until = time.monotonic() + self.cooldown
        return getattr(self.fallback, name)(*args, **kwargs)

    def ping(self) -> bool:
        try:
            return bool(self.primary.ping())
        except Exception:  # noqa: BLE001
            return False

    def close(self) -> None:
        try:
            self.primary.close()
        except Exception:  # noqa: BLE001
            pass

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *a, **kw: self._call(name, *a, **kw)
