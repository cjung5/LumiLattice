"""Candidate stores: in memory (default) or SQL (Postgres in production, SQLite in tests).

Render's free plan deletes local files when the service sleeps, so set DATABASE_URL to a
hosted Postgres (e.g. Neon or Supabase) to keep candidates, decisions, and history.
"""

import json
from collections.abc import Callable
from functools import lru_cache
from threading import Lock
from typing import Any, Protocol

from pymatgen.core import Structure
from sqlalchemy import Column, Integer, MetaData, String, Table, Text, create_engine, func, select

from app.config import get_settings
from app.models.candidates import Candidate, Decision

Build = Callable[[str], tuple[Candidate, Structure]]


class CandidateStore(Protocol):
    def add(self, build: Build) -> Candidate: ...
    def get(self, candidate_id: str) -> tuple[Candidate, Structure] | None: ...
    def update(self, candidate_id: str, changes: dict[str, Any]) -> Candidate | None: ...
    def all(self) -> list[Candidate]: ...


def add_decision(store: CandidateStore, candidate_id: str, decision: Decision) -> Candidate | None:
    stored = store.get(candidate_id)
    if stored is None:
        return None
    return store.update(candidate_id, {"decisions": [*stored[0].decisions, decision]})


class MemoryStore:
    def __init__(self) -> None:
        self._items: dict[str, tuple[Candidate, Structure]] = {}
        self._next = 1
        self._lock = Lock()

    def add(self, build: Build) -> Candidate:
        with self._lock:
            candidate_id = f"LL-{self._next:04d}"
            self._next += 1
        candidate, structure = build(candidate_id)
        with self._lock:
            self._items[candidate_id] = (candidate, structure)
        return candidate

    def get(self, candidate_id: str) -> tuple[Candidate, Structure] | None:
        with self._lock:
            return self._items.get(candidate_id)

    def update(self, candidate_id: str, changes: dict[str, Any]) -> Candidate | None:
        with self._lock:
            stored = self._items.get(candidate_id)
            if stored is None:
                return None
            updated = stored[0].model_copy(update=changes)
            self._items[candidate_id] = (updated, stored[1])
            return updated

    def all(self) -> list[Candidate]:
        with self._lock:
            return [candidate for candidate, _ in self._items.values()]


metadata = MetaData()
candidates_table = Table(
    "candidates",
    metadata,
    Column("id", String(20), primary_key=True),
    Column("seq", Integer, unique=True, nullable=False),
    Column("data", Text, nullable=False),  # Candidate as JSON
    Column("structure", Text, nullable=False),  # pymatgen Structure.as_dict() as JSON
)


def sqlalchemy_url(url: str) -> str:
    """Neon and Supabase give postgres:// URLs; SQLAlchemy needs the psycopg 3 driver name."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url.removeprefix(prefix)
    return url


class SqlStore:
    def __init__(self, url: str):
        self._engine = create_engine(sqlalchemy_url(url), pool_pre_ping=True)
        metadata.create_all(self._engine)
        self._lock = Lock()  # one app process: serialize ID allocation

    def add(self, build: Build) -> Candidate:
        with self._lock, self._engine.begin() as conn:
            seq = (conn.execute(select(func.max(candidates_table.c.seq))).scalar() or 0) + 1
            candidate, structure = build(f"LL-{seq:04d}")
            conn.execute(
                candidates_table.insert().values(
                    id=candidate.candidate_id,
                    seq=seq,
                    data=candidate.model_dump_json(),
                    structure=json.dumps(structure.as_dict()),
                )
            )
        return candidate

    def get(self, candidate_id: str) -> tuple[Candidate, Structure] | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(candidates_table.c.data, candidates_table.c.structure).where(
                    candidates_table.c.id == candidate_id
                )
            ).first()
        if row is None:
            return None
        return Candidate.model_validate_json(row.data), Structure.from_dict(
            json.loads(row.structure)
        )

    def update(self, candidate_id: str, changes: dict[str, Any]) -> Candidate | None:
        with self._lock, self._engine.begin() as conn:
            data = conn.execute(
                select(candidates_table.c.data).where(candidates_table.c.id == candidate_id)
            ).scalar()
            if data is None:
                return None
            updated = Candidate.model_validate_json(data).model_copy(update=changes)
            conn.execute(
                candidates_table.update()
                .where(candidates_table.c.id == candidate_id)
                .values(data=updated.model_dump_json())
            )
        return updated

    def all(self) -> list[Candidate]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(candidates_table.c.data).order_by(candidates_table.c.seq)
            ).scalars()
            return [Candidate.model_validate_json(data) for data in rows]


@lru_cache
def get_store() -> CandidateStore:
    url = get_settings().database_url
    return SqlStore(url.get_secret_value()) if url else MemoryStore()
