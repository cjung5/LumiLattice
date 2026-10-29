"""In-memory candidate store (priority level 1). Hosted Postgres replaces it in level 2."""

from collections.abc import Callable
from threading import Lock

from pymatgen.core import Structure

from app.models.candidates import Candidate


class CandidateStore:
    def __init__(self) -> None:
        self._items: dict[str, tuple[Candidate, Structure]] = {}
        self._next = 1
        self._lock = Lock()

    def add(self, build: Callable[[str], tuple[Candidate, Structure]]) -> Candidate:
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

    def all(self) -> list[Candidate]:
        with self._lock:
            return [candidate for candidate, _ in self._items.values()]


STORE = CandidateStore()
