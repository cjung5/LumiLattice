"""Candidate creation: substitute on a host, then assess (spec 3.3 and 3.4)."""

import itertools
from datetime import UTC, datetime

from pymatgen.core import Composition, Structure

from app.models.candidates import Candidate, StructuralAssessment, Substitution, Transformation
from app.models.evidence import Provenance
from app.storage.memory import CandidateStore
from app.tools.materials import MaterialsProjectClient
from app.tools.reference_db import ReferenceDB, get_reference_db
from app.tools.registry import ToolError, UpstreamError
from app.tools.structures import CELL_METHOD, parse_cif_structure, structure_payload
from app.tools.substitution import (
    SITE_SELECTION,
    Arrangement,
    substitute,
    substitute_lowest_ewald,
)
from app.tools.validation import AnalogLookup, assess


def load_host(
    store: CandidateStore,
    mp: MaterialsProjectClient | None,
    *,
    material_id: str | None = None,
    candidate_id: str | None = None,
    cif: str | None = None,
    filename: str = "upload.cif",
) -> tuple[Structure, Provenance, str | None]:
    """Host structure, its provenance, and the parent candidate ID (for revisions)."""
    if sum(x is not None for x in (material_id, candidate_id, cif)) != 1:
        raise ToolError("Give exactly one host: a Materials Project ID, a candidate ID, or a CIF.")
    if candidate_id is not None:
        stored = store.get(candidate_id)
        if stored is None:
            raise ToolError(f"No candidate {candidate_id}.")
        return (
            stored[1],
            Provenance(source="LumiLattice candidate", reference=candidate_id),
            candidate_id,
        )
    if material_id is not None:
        if mp is None:
            raise UpstreamError("Materials Project is not configured (MP_API_KEY missing).")
        host = mp.get_structure(material_id)
        provenance = Provenance(
            source="Materials Project", method=CELL_METHOD, reference=material_id
        )
        return host, provenance, None
    host = parse_cif_structure(cif or "", filename)
    return host, Provenance(source="CIF upload", reference=filename), None


def _chained_ends(root_formula: str, lineage: list[Substitution]) -> list[str] | None:
    """End members of a revision that swapped atoms that an earlier step put in. None if no step did.

    The substitutions are followed site by site. SrTiO3 + Sr->La + Ti->Al + Al->Ti 100 % has no Al
    left, so it lies between SrTiO3 and LaTiO3. The first formula uses the element that came first
    on each site family, and the others change one family, or all that vary, at a time.
    """
    base = Composition(root_formula).reduced_composition.as_dict()
    if all(s.element_from in base for s in lineage):
        return None
    families = {site: {site: 1.0} for site in base}
    for s in lineage:
        for family in families.values():
            moved = family.get(s.element_from, 0.0) * s.fraction
            if moved > 0:
                family[s.element_from] -= moved
                family[s.element_to] = family.get(s.element_to, 0.0) + moved
    members = {
        site: [el for el, share in f.items() if share > 1e-6] for site, f in families.items()
    }

    def formula(choice: dict[str, str]) -> str:
        amounts: dict[str, float] = {}
        for site, n in base.items():
            amounts[choice[site]] = amounts.get(choice[site], 0.0) + n
        return Composition(amounts).reduced_formula

    first = {site: found[0] for site, found in members.items()}
    varied = [site for site, found in members.items() if len(found) > 1]
    others = itertools.product(*(members[site][1:] for site in varied))
    if len(varied) == 1:
        ends = [formula(first | {varied[0]: el}) for el in members[varied[0]][1:]]
    else:
        ends = [
            formula(first | dict(zip(varied, combo, strict=True)))
            for combo in itertools.islice(others, 8)
        ]
    return list(dict.fromkeys([formula(first), *ends]))


def end_member_formulas(root_formula: str, lineage: list[Substitution]) -> list[str]:
    """Root host with substitutions taken to 100 %: all of them together, then each alone.

    SrTiO3 + Sr->La + Ti->Al gives LaAlO3 (together), LaTiO3, and SrAlO3.
    """
    chained = _chained_ends(root_formula, lineage)
    if chained is not None:
        return [f for f in chained if f != root_formula] or chained
    base = Composition(root_formula).reduced_composition.as_dict()

    def swap(subs: list[Substitution]) -> str:
        mapping = {s.element_from: s.element_to for s in subs}
        return Composition({mapping.get(el, el): n for el, n in base.items()}).reduced_formula

    formulas = [swap(lineage)] if len({s.element_from for s in lineage}) > 1 else []
    formulas += [swap([s]) for s in lineage]
    return list(dict.fromkeys(formulas))


def solid_solution_ends(root_formula: str, lineage: list[Substitution]) -> list[str]:
    """Compounds a candidate lies between: SrTiO3 + Sr->La + Ti->Al lies between SrTiO3 and
    LaAlO3; SrTiO3 + Ti->Zr + Ti->Hf lies among SrTiO3, SrZrO3, and SrHfO3."""
    chained = _chained_ends(root_formula, lineage)
    if chained is not None:
        return chained
    ends = end_member_formulas(root_formula, lineage)
    if len({s.element_from for s in lineage}) > 1:
        ends = ends[:1]
    return [root_formula, *ends]


def mp_analog_lookup(mp: MaterialsProjectClient | None) -> AnalogLookup | None:
    if mp is None:
        return None

    def lookup(formula: str) -> list[str]:
        try:
            return [r.material_id for r in mp.search(formula=formula, limit=3)]
        except ToolError:
            return []

    return lookup


def assess_host(host: Structure, mp: MaterialsProjectClient | None = None) -> StructuralAssessment:
    formula = host.composition.reduced_formula
    return assess(host, None, [formula], mp_analog_lookup(mp))


def create_candidate(
    store: CandidateStore,
    host: Structure,
    host_ref: Provenance,
    subs: list[Substitution],
    parent_id: str | None = None,
    mp: MaterialsProjectClient | None = None,
    reference: ReferenceDB | None = None,
    arrangement: Arrangement = "spread",
) -> Candidate:
    reference = reference or get_reference_db()
    parent = store.get(parent_id)[0] if parent_id else None
    if parent:
        root_formula = parent.transformation.root_formula
        lineage = [*parent.transformation.lineage, *subs]
    else:
        root_formula, lineage = host.composition.reduced_formula, list(subs)

    if arrangement == "lowest_ewald":
        structure, supercell, replaced, site_selection = substitute_lowest_ewald(host, subs)
    else:
        structure, supercell, replaced = substitute(host, subs)
        site_selection = SITE_SELECTION
    focus = sorted(i for sites in replaced.values() for i in sites)
    assessment = assess(
        structure, focus, end_member_formulas(root_formula, lineage), mp_analog_lookup(mp)
    )
    optical = reference.estimate(
        solid_solution_ends(root_formula, lineage), exact=structure.composition.reduced_formula
    )

    # Work from someone else's published candidate keeps their credit, through any later revisions.
    based_on = None
    if parent:
        based_on = parent.credit if parent.credit and not parent.mine else parent.based_on_credit

    def build(candidate_id: str) -> tuple[Candidate, Structure]:
        payload = structure_payload(
            structure, Provenance(source="LumiLattice substitution", reference=candidate_id)
        )
        candidate = Candidate(
            candidate_id=candidate_id,
            parent_id=parent_id,
            formula=structure.composition.reduced_formula,
            structure=payload,
            transformation=Transformation(
                host=host_ref,
                supercell=supercell,
                substitutions=subs,
                substituted_sites=replaced,
                site_selection=site_selection,
                arrangement=arrangement,
                root_formula=root_formula,
                lineage=lineage,
            ),
            assessment=assessment,
            optical_estimate=optical,
            created_at=datetime.now(UTC),
            based_on_credit=based_on,
        )
        return candidate, structure

    return store.add(build)
