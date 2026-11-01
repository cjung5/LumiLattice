"""Is this material already public? Checked before an owner publishes a candidate.

The same material means the same composition on the same crystal framework. Atom arrangement does
not count: an ordered cell is one model of a disordered solid, so two arrangements of the same
atoms are one material. Rutile and anatase forms of a composition have different frameworks, so
they are two materials. Only public candidates are compared, so this never shows a private one.
"""

from pydantic import BaseModel
from pymatgen.analysis.structure_matcher import FrameworkComparator, StructureMatcher
from pymatgen.core import Structure

from app.models.candidates import Candidate, Credit
from app.storage.scoped import ScopedStore

_MATCHER = StructureMatcher(
    primitive_cell=True, scale=True, attempt_supercell=True, comparator=FrameworkComparator()
)


class PublicMatch(BaseModel):
    candidate_id: str
    credit: Credit | None = None


class PublicMatches(BaseModel):
    already_public: list[
        PublicMatch
    ]  # owned and published: this material cannot be published again
    other_framework: list[PublicMatch]  # the same composition, but another crystal form
    unclaimed: list[PublicMatch]  # public-mode copies with no owner: these do not stop publishing


def _same_framework(a: Structure, b: Structure) -> bool:
    try:
        return _MATCHER.fit(a, b)
    except Exception:  # noqa: BLE001 - if the comparison fails, keep to the same-composition answer
        return True


def public_matches(store: ScopedStore, candidate: Candidate, structure: Structure) -> PublicMatches:
    result = PublicMatches(already_public=[], other_framework=[], unclaimed=[])
    for other in store.all():
        if other.candidate_id == candidate.candidate_id or other.formula != candidate.formula:
            continue
        owned = other.mine or not other.editable
        if owned and other.visibility != "published":
            continue  # the viewer's own private copy
        stored = store.get(other.candidate_id)
        if stored is None or not _same_framework(structure, stored[1]):
            result.other_framework.append(
                PublicMatch(candidate_id=other.candidate_id, credit=other.credit)
            )
        elif owned:
            result.already_public.append(
                PublicMatch(candidate_id=other.candidate_id, credit=other.credit)
            )
        else:
            result.unclaimed.append(PublicMatch(candidate_id=other.candidate_id))
    return result
