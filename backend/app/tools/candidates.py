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


def end_member_formulas(root_formula: str, lineage: list[Substitution]) -> list[str]:
    """Root host with substitutions taken to 100 %: all of them together, then each alone.

    SrTiO3 + Sr->La + Ti->Al gives LaAlO3 (together), LaTiO3, and SrAlO3.
    """
    base = Composition(root_formula).reduced_composition.as_dict()

    def swap(subs: list[Substitution]) -> str:
        mapping = {s.element_from: s.element_to for s in subs}
        return Composition({mapping.get(el, el): n for el, n in base.items()}).reduced_formula

    formulas = [swap(lineage)] if len({s.element_from for s in lineage}) > 1 else []
    formulas += [swap([s]) for s in lineage]
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
    parent = store.get(parent_id)[0] if parent_id else None
    if parent:
        root_formula = parent.transformation.root_formula
        lineage = [*parent.transformation.lineage, *subs]
    else:
        root_formula, lineage = host.composition.reduced_formula, list(subs)

    structure, supercell, replaced = substitute(host, subs)
    focus = sorted(i for sites in replaced.values() for i in sites)
    assessment = assess(
        structure, focus, end_member_formulas(root_formula, lineage), mp_analog_lookup(mp)
    )

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
                root_formula=root_formula,
                lineage=lineage,
            ),
            assessment=assessment,
            created_at=datetime.now(UTC),
        )
        return candidate, structure

    return store.add(build)
