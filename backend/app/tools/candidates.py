"""Candidate creation: substitute on a host, then assess (spec 3.3 and 3.4)."""

from datetime import UTC, datetime

from pymatgen.core import Composition, Structure

from app.models.candidates import Candidate, StructuralAssessment, Substitution, Transformation
from app.models.evidence import Provenance
from app.storage.memory import CandidateStore
from app.tools.materials import MaterialsProjectClient
from app.tools.registry import ToolError, UpstreamError
from app.tools.structures import parse_cif_structure, structure_payload
from app.tools.substitution import SITE_SELECTION, substitute
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
        return host, Provenance(source="Materials Project", reference=material_id), None
    host = parse_cif_structure(cif or "", filename)
    return host, Provenance(source="CIF upload", reference=filename), None


def end_member_formulas(host: Structure, subs: list[Substitution]) -> list[str]:
    """Formulas with each substitution taken to 100 %, e.g. SrTiO3 + Ti->Zr gives SrZrO3."""
    base = host.composition.reduced_composition.as_dict()
    formulas = []
    for sub in subs:
        swapped = {(sub.element_to if el == sub.element_from else el): n for el, n in base.items()}
        formulas.append(Composition(swapped).reduced_formula)
    return list(dict.fromkeys(formulas))


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
) -> Candidate:
    structure, supercell, replaced = substitute(host, subs)
    focus = sorted(i for sites in replaced.values() for i in sites)
    assessment = assess(structure, focus, end_member_formulas(host, subs), mp_analog_lookup(mp))

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
                site_selection=SITE_SELECTION,
            ),
            assessment=assessment,
            created_at=datetime.now(UTC),
        )
        return candidate, structure

    return store.add(build)
