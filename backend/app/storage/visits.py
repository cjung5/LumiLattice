"""Visitor counts by country, for the globe at the bottom of the page.

Only a two-letter country code and a count are kept: no IP address, no browser details, no time.
Without DATABASE_URL the counts live in memory and reset when the server restarts.
"""

from functools import lru_cache
from threading import Lock
from typing import Protocol

from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, select, update
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.storage.memory import sqlalchemy_url

UNKNOWN = "ZZ"  # ISO 3166 "user-assigned" code: the hosting service did not give a country.


class VisitCounts(Protocol):
    persistent: bool

    def add(self, country: str | None) -> None: ...
    def counts(self) -> dict[str, int]: ...


class MemoryVisits:
    persistent = False

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._lock = Lock()

    def add(self, country: str | None) -> None:
        code = country or UNKNOWN
        with self._lock:
            self._counts[code] = self._counts.get(code, 0) + 1

    def counts(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counts)


metadata = MetaData()
visits_table = Table(
    "visits_by_country",
    metadata,
    Column("country", String(2), primary_key=True),
    Column("count", Integer, nullable=False),
)


class SqlVisits:
    persistent = True

    def __init__(self, url: str):
        self._engine = create_engine(sqlalchemy_url(url), pool_pre_ping=True)
        metadata.create_all(self._engine)

    def _increment(self, code: str) -> int:
        with self._engine.begin() as conn:
            return conn.execute(
                update(visits_table)
                .where(visits_table.c.country == code)
                .values(count=visits_table.c.count + 1)
            ).rowcount

    def add(self, country: str | None) -> None:
        code = country or UNKNOWN
        if self._increment(code):
            return
        try:
            with self._engine.begin() as conn:
                conn.execute(visits_table.insert().values(country=code, count=1))
        except IntegrityError:  # another request added this country first
            self._increment(code)

    def counts(self) -> dict[str, int]:
        with self._engine.connect() as conn:
            return {row.country: row.count for row in conn.execute(select(visits_table))}


@lru_cache
def get_visits() -> VisitCounts:
    url = get_settings().database_url
    return SqlVisits(url.get_secret_value()) if url else MemoryVisits()
