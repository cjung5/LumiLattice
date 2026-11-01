"""One viewer's view of the candidate store. Every API path and agent tool reads through this.

An owned candidate is hidden from others until it is published, and only its owner can change it.
A candidate with no owner (public mode) stays open to everyone. The owner's ID never leaves this
class, because anonymous credit must stay anonymous.
"""

from typing import Any

from pymatgen.core import Structure

from app.auth import Viewer
from app.models.candidates import Candidate
from app.storage.memory import Build, CandidateStore


class NotOwner(Exception):
    pass


class ScopedStore:
    def __init__(self, store: CandidateStore, viewer: Viewer | None):
        self._store = store
        self.viewer = viewer

    def _mine(self, candidate: Candidate) -> bool:
        return self.viewer is not None and candidate.owner_id == self.viewer.id

    def _readable(self, candidate: Candidate) -> bool:
        return (
            candidate.owner_id is None
            or candidate.visibility == "published"
            or self._mine(candidate)
        )

    def _view(self, candidate: Candidate) -> Candidate:
        mine = self._mine(candidate)
        editable = candidate.owner_id is None or mine
        return candidate.model_copy(
            update={
                "owner_id": None,
                "mine": mine,
                "editable": editable,
                # An earlier publication can have a name that the owner later made anonymous.
                "publications": candidate.publications if editable else [],
            }
        )

    def add(self, build: Build) -> Candidate:
        def owned(candidate_id: str) -> tuple[Candidate, Structure]:
            candidate, structure = build(candidate_id)
            owner = self.viewer.id if self.viewer else None
            return candidate.model_copy(update={"owner_id": owner}), structure

        return self._view(self._store.add(owned))

    def get(self, candidate_id: str) -> tuple[Candidate, Structure] | None:
        stored = self._store.get(candidate_id)
        if stored is None or not self._readable(stored[0]):
            return None
        return self._view(stored[0]), stored[1]

    def update(self, candidate_id: str, changes: dict[str, Any]) -> Candidate | None:
        stored = self._store.get(candidate_id)
        if stored is None or not self._readable(stored[0]):
            return None
        if stored[0].owner_id is not None and not self._mine(stored[0]):
            raise NotOwner(candidate_id)
        updated = self._store.update(candidate_id, changes)
        return None if updated is None else self._view(updated)

    def all(self) -> list[Candidate]:
        return [self._view(c) for c in self._store.all() if self._readable(c)]
