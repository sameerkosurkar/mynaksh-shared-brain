"""Writes extracted facts into the Shared Brain.

Update policy
-------------
* New key                         -> create node.
* Same key, same/no new details   -> reinforce (mention_count+1, confidence up, updated_at refreshed).
* Same key, different details     -> create a new version and link (new)-[:SUPERSEDES]->(old);
                                     old version is kept with status 'superseded' (audit trail).
* "I'm no longer planning to ..." -> mark the existing goal 'abandoned' (never silently deleted).
* Profile field changed           -> overwrite, record a ProfileHistory node; DOB change recomputes zodiac.
* Low-confidence candidates       -> not stored.
Similar titles within the same kind+area (token Jaccard >= 0.6) are treated as the same memory.
"""
from __future__ import annotations

import logging
import re

from app.brain.models import ABANDONED, MemoryItem, utcnow_iso
from app.memory.extractor import Candidate, Extraction
from app.profile.astrology import parse_iso_date, sun_sign

log = logging.getLogger(__name__)

_IGNORED_ATTRS = {"when"}


def _tokens(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", s.lower())) - {"a", "an", "the", "my", "to", "of"}


def _similar(a: str, b: str) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    return bool(ta and tb) and len(ta & tb) / len(ta | tb) >= 0.6


class MemoryUpdater:
    def __init__(self, store, min_confidence: float = 0.5):
        self.store = store
        self.min_confidence = min_confidence

    def apply(self, user_id: str, extraction: Extraction) -> list[dict]:
        updates: list[dict] = []
        if extraction.profile:
            updates += self._apply_profile(user_id, extraction.profile)
        for cand in extraction.items:
            try:
                upd = self._apply_item(user_id, cand)
            except Exception:  # noqa: BLE001 - one bad memory must not lose the others
                log.exception("failed to store memory %s", cand.key)
                continue
            if upd:
                updates.append(upd)
        return updates

    # -- profile ---------------------------------------------------------------
    def _apply_profile(self, user_id: str, profile: dict) -> list[dict]:
        existing = self.store.get_user(user_id) or {}
        changed, updates = {}, []
        for fld, value in profile.items():
            old = existing.get(fld)
            if old == value:
                continue
            changed[fld] = value
            if old:
                self.store.record_profile_change(user_id, fld, old, value)
                updates.append({"action": "corrected", "kind": "profile", "key": f"profile:{fld}",
                                "title": fld, "detail": f"{old} -> {value}"})
            else:
                updates.append({"action": "created", "kind": "profile", "key": f"profile:{fld}",
                                "title": fld, "detail": str(value)})
        if changed:
            self.store.upsert_user(user_id, changed)
            if "date_of_birth" in changed:
                sign = sun_sign(parse_iso_date(changed["date_of_birth"]))
                self.store.set_zodiac(user_id, sign)
                if sign:
                    updates.append({"action": "created" if not existing.get("sun_sign") else "corrected",
                                    "kind": "astrology", "key": "zodiac", "title": "sun_sign", "detail": sign})
        return updates

    # -- items -------------------------------------------------------------------
    def _find_existing(self, user_id: str, cand: Candidate) -> MemoryItem | None:
        found = self.store.find_active_item(user_id, cand.key)
        if found:
            return found
        for it in self.store.get_items(user_id, areas=[cand.area], kinds=[cand.kind]):
            if _similar(it.title, cand.title):
                return it
        return None

    def _apply_item(self, user_id: str, cand: Candidate) -> dict | None:
        if cand.confidence < self.min_confidence:
            return None
        existing = self._find_existing(user_id, cand)
        base = {"kind": cand.kind, "key": cand.key, "title": cand.title}

        if cand.status == ABANDONED:
            if not existing:
                return None
            existing.status, existing.updated_at = ABANDONED, utcnow_iso()
            self.store.upsert_item(user_id, existing)
            return {**base, "action": "abandoned", "title": existing.title, "detail": "user no longer pursuing this"}

        if existing is None:
            item = MemoryItem(kind=cand.kind, key=cand.key, title=cand.title, area=cand.area,
                              attributes=cand.attributes, confidence=cand.confidence,
                              importance=cand.importance, source_text=cand.source_text)
            self.store.upsert_item(user_id, item)
            return {**base, "action": "created", "detail": item.describe()}

        new_attrs = {k: v for k, v in cand.attributes.items() if k not in _IGNORED_ATTRS}
        old_attrs = {k: v for k, v in existing.attributes.items() if k not in _IGNORED_ATTRS}
        conflicting = any(k in old_attrs and old_attrs[k] != v for k, v in new_attrs.items())

        if not conflicting:
            existing.mention_count += 1
            existing.confidence = round(min(0.99, max(existing.confidence, cand.confidence) + 0.05), 2)
            existing.importance = max(existing.importance, cand.importance)
            existing.attributes = {**existing.attributes, **cand.attributes}
            existing.updated_at = utcnow_iso()
            self.store.upsert_item(user_id, existing)
            return {**base, "action": "reinforced", "title": existing.title, "detail": existing.describe()}

        # Conflict -> new version supersedes the old one (history kept)
        new = MemoryItem(kind=cand.kind, key=existing.key, title=cand.title, area=cand.area,
                         attributes=cand.attributes, confidence=max(cand.confidence, 0.85),
                         importance=max(existing.importance, cand.importance), source_text=cand.source_text,
                         mention_count=existing.mention_count + 1)
        self.store.upsert_item(user_id, new)
        self.store.link_supersedes(new.id, existing.id)
        return {**base, "action": "updated", "detail": f"{existing.describe()} -> {new.describe()}"}
