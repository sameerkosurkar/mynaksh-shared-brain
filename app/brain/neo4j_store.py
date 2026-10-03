"""Neo4j implementation of the Shared Brain.

Graph model
-----------
(:User {user_id, name, date_of_birth, time_of_birth, birth_place, preferred_language})
  -[:HAS_ZODIAC]->        (:ZodiacSign {name, element, ruling_planet})
  -[:HAS_GOAL]->          (:Memory:Goal       {id, key, title, area, status, confidence, importance, attr_*})
  -[:INTERESTED_IN]->     (:Memory:Interest   {...})
  -[:PREFERS]->           (:Memory:Preference {...})
  -[:EXPERIENCED]->       (:Memory:LifeEvent  {...})
  -[:CONCERNED_ABOUT]->   (:Memory:Concern    {...})
  -[:HAD_SESSION]->       (:Session {session_id, summary, turns, started_at, last_active})
  -[:HAD_PROFILE_VALUE]-> (:ProfileHistory {field, old_value, new_value, changed_at})
(:Memory)-[:ABOUT]->(:LifeArea {name})
(:Memory)-[:SUPERSEDES]->(:Memory)     # correction history; old node keeps status='superseded'

Labels/relationship types cannot be Cypher parameters, so they are taken from the KIND_SCHEMA
whitelist only - never from user input.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

from neo4j import GraphDatabase, RoutingControl

from app.brain.models import ACTIVE, KIND_SCHEMA, SUPERSEDED, MemoryItem, utcnow_iso
from app.brain.store import _brain_view
from app.profile.astrology import SIGN_INFO

log = logging.getLogger(__name__)

_SCHEMA = [
    "CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.user_id IS UNIQUE",
    "CREATE CONSTRAINT memory_id IF NOT EXISTS FOR (m:Memory) REQUIRE m.id IS UNIQUE",
    "CREATE CONSTRAINT life_area IF NOT EXISTS FOR (a:LifeArea) REQUIRE a.name IS UNIQUE",
    "CREATE CONSTRAINT zodiac IF NOT EXISTS FOR (z:ZodiacSign) REQUIRE z.name IS UNIQUE",
    "CREATE CONSTRAINT session_id IF NOT EXISTS FOR (s:Session) REQUIRE s.session_id IS UNIQUE",
    "CREATE INDEX memory_key IF NOT EXISTS FOR (m:Memory) ON (m.key, m.status)",
]


class Neo4jGraphStore:
    def __init__(self, uri: str, user: str, password: str, database: str = "neo4j"):
        self.driver = GraphDatabase.driver(uri, auth=(user, password), connection_timeout=5.0,
                                           max_connection_lifetime=300)
        self.database = database
        self._schema_ready = False

    # -- helpers -------------------------------------------------------------
    def _run(self, query: str, read: bool = False, **params) -> list[dict]:
        if not self._schema_ready:
            self._ensure_schema()
        records, _, _ = self.driver.execute_query(
            query, params, database_=self.database,
            routing_=RoutingControl.READ if read else RoutingControl.WRITE)
        return [r.data() for r in records]

    def _ensure_schema(self) -> None:
        for stmt in _SCHEMA:
            self.driver.execute_query(stmt, database_=self.database)
        self._schema_ready = True

    # -- GraphStore ----------------------------------------------------------
    def ping(self) -> bool:
        self.driver.verify_connectivity()
        return True

    def get_user(self, user_id: str) -> Optional[dict]:
        rows = self._run(
            "MATCH (u:User {user_id: $uid}) OPTIONAL MATCH (u)-[:HAS_ZODIAC]->(z:ZodiacSign) "
            "RETURN u{.*} AS user, z.name AS sign", read=True, uid=user_id)
        if not rows:
            return None
        return {**rows[0]["user"], "sun_sign": rows[0]["sign"]}

    def upsert_user(self, user_id: str, props: dict) -> dict:
        clean = {k: v for k, v in props.items() if v is not None}
        rows = self._run(
            "MERGE (u:User {user_id: $uid}) ON CREATE SET u.created_at = $now "
            "SET u += $props, u.updated_at = $now RETURN u{.*} AS user",
            uid=user_id, props=clean, now=utcnow_iso())
        return rows[0]["user"]

    def set_zodiac(self, user_id: str, sign: Optional[str]) -> None:
        self._run("MATCH (u:User {user_id: $uid})-[r:HAS_ZODIAC]->() DELETE r", uid=user_id)
        if sign:
            info = SIGN_INFO.get(sign, {})
            self._run(
                "MATCH (u:User {user_id: $uid}) MERGE (z:ZodiacSign {name: $sign}) "
                "SET z.element = $element, z.ruling_planet = $planet MERGE (u)-[:HAS_ZODIAC]->(z)",
                uid=user_id, sign=sign, element=info.get("element"), planet=info.get("ruling_planet"))

    def record_profile_change(self, user_id: str, field: str, old: Any, new: Any) -> None:
        self._run(
            "MATCH (u:User {user_id: $uid}) CREATE (u)-[:HAD_PROFILE_VALUE]->"
            "(:ProfileHistory {field: $field, old_value: $old, new_value: $new, changed_at: $now})",
            uid=user_id, field=field, old=str(old), new=str(new), now=utcnow_iso())

    def upsert_item(self, user_id: str, item: MemoryItem) -> None:
        label, rel = KIND_SCHEMA[item.kind]
        self._run(
            f"MATCH (u:User {{user_id: $uid}}) "
            f"MERGE (m:Memory:{label} {{id: $id}}) SET m = $props "
            f"MERGE (u)-[:{rel}]->(m) "
            f"MERGE (a:LifeArea {{name: $area}}) MERGE (m)-[:ABOUT]->(a)",
            uid=user_id, id=item.id, props=item.to_props(), area=item.area)

    def find_active_item(self, user_id: str, key: str) -> Optional[MemoryItem]:
        rows = self._run(
            "MATCH (:User {user_id: $uid})-->(m:Memory {key: $key, status: $active}) "
            "RETURN m{.*} AS m ORDER BY m.updated_at DESC LIMIT 1",
            read=True, uid=user_id, key=key, active=ACTIVE)
        return MemoryItem.from_props(rows[0]["m"]) if rows else None

    def link_supersedes(self, new_id: str, old_id: str) -> None:
        self._run(
            "MATCH (n:Memory {id: $new}), (o:Memory {id: $old}) "
            "SET o.status = $superseded, o.updated_at = $now MERGE (n)-[:SUPERSEDES]->(o)",
            new=new_id, old=old_id, superseded=SUPERSEDED, now=utcnow_iso())

    def get_items(self, user_id, areas=None, kinds=None, statuses=(ACTIVE,), limit=50):
        # Traverses User -> Memory -> LifeArea so that area filtering uses the graph structure.
        rows = self._run(
            "MATCH (:User {user_id: $uid})-->(m:Memory)-[:ABOUT]->(a:LifeArea) "
            "WHERE m.status IN $statuses "
            "AND ($areas IS NULL OR a.name IN $areas) AND ($kinds IS NULL OR m.kind IN $kinds) "
            "RETURN m{.*} AS m ORDER BY m.importance DESC, m.updated_at DESC LIMIT $limit",
            read=True, uid=user_id, statuses=list(statuses),
            areas=list(areas) if areas else None, kinds=list(kinds) if kinds else None, limit=limit)
        return [MemoryItem.from_props(r["m"]) for r in rows]

    def record_session(self, user_id: str, session_id: str, summary: str, turns: int) -> None:
        now = utcnow_iso()
        self._run(
            "MATCH (u:User {user_id: $uid}) "
            "MERGE (s:Session {session_id: $sid}) ON CREATE SET s.started_at = $now, s.user_id = $uid "
            "SET s.summary = $summary, s.turns = $turns, s.last_active = $now "
            "MERGE (u)-[:HAD_SESSION]->(s)",
            uid=user_id, sid=session_id, summary=summary, turns=turns, now=now)

    def get_recent_sessions(self, user_id, exclude_session_id=None, limit=2):
        rows = self._run(
            "MATCH (:User {user_id: $uid})-[:HAD_SESSION]->(s:Session) "
            "WHERE $exclude IS NULL OR s.session_id <> $exclude "
            "RETURN s{.*} AS s ORDER BY s.last_active DESC LIMIT $limit",
            read=True, uid=user_id, exclude=exclude_session_id, limit=limit)
        return [r["s"] for r in rows]

    def get_brain(self, user_id: str) -> Optional[dict]:
        user = self.get_user(user_id)
        if user is None:
            return None
        items = self.get_items(user_id, statuses=(ACTIVE, SUPERSEDED, "abandoned"), limit=1000)
        sup = self._run(
            "MATCH (:User {user_id: $uid})-->(n:Memory)-[:SUPERSEDES]->(o:Memory) "
            "RETURN n.id AS new_id, o.id AS old_id", read=True, uid=user_id)
        hist = self._run(
            "MATCH (:User {user_id: $uid})-[:HAD_PROFILE_VALUE]->(h) RETURN h{.*} AS h "
            "ORDER BY h.changed_at", read=True, uid=user_id)
        return _brain_view(user, user.get("sun_sign"), items,
                           [(r["new_id"], r["old_id"]) for r in sup], [r["h"] for r in hist],
                           self.get_recent_sessions(user_id, limit=20))

    def delete_user(self, user_id: str) -> bool:
        rows = self._run(
            "MATCH (u:User {user_id: $uid}) "
            "OPTIONAL MATCH (u)-->(n) WHERE n:Memory OR n:Session OR n:ProfileHistory "
            "WITH u, collect(n) AS owned FOREACH (x IN owned | DETACH DELETE x) "
            "DETACH DELETE u RETURN 1 AS c", uid=user_id)
        return bool(rows and rows[0]["c"])

    def close(self) -> None:
        self.driver.close()
