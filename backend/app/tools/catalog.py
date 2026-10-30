"""The set of tools the research agent can call."""

from typing import Any

from pydantic import BaseModel, Field

from app.models.candidates import Candidate, Substitution
from app.storage.memory import CandidateStore, get_store
from app.tools.candidates import create_candidate, load_host
from app.tools.composition import COMPOSITION_TOOL
from app.tools.literature_sources import LiteratureSearch
from app.tools.materials import MaterialsProjectClient
from app.tools.reference_db import get_reference_db
from app.tools.registry import Tool, ToolError, ToolRegistry


class SearchMaterialsArgs(BaseModel):
    formula: str | None = Field(
        default=None,
        max_length=60,
        description="Formula, e.g. 'SrTiO3'. Wildcards are allowed, e.g. '*TiO3'.",
    )
    elements: list[str] | None = Field(
        default=None,
        max_length=8,
        description="Elements that must all be present, e.g. ['Sr', 'Ti', 'O'].",
    )
    band_gap_min: float | None = Field(
        default=None, ge=0, le=20, description="Minimum DFT band gap in eV."
    )
    limit: int = Field(default=5, ge=1, le=10)


class SearchLiteratureArgs(BaseModel):
    query: str = Field(
        min_length=2, max_length=200, description="Search words, e.g. a formula and a property."
    )
    limit: int = Field(default=5, ge=1, le=10)


class CreateCandidateArgs(BaseModel):
    host_material_id: str | None = Field(
        default=None, max_length=40, description="Materials Project ID of the host, e.g. 'mp-5229'."
    )
    host_candidate_id: str | None = Field(
        default=None,
        max_length=20,
        description="ID of an earlier candidate to revise, e.g. 'LL-0001'. Use instead of host_material_id.",
    )
    substitutions: list[Substitution] = Field(
        min_length=1,
        max_length=4,
        description="Element replacements, e.g. [{'element_from': 'Ti', 'element_to': 'Zr', 'fraction': 0.5}]. "
        "Fractions like 1, 1/2, 1/3, 1/4 work best.",
    )


class OpticalReferenceArgs(BaseModel):
    formula: str = Field(min_length=1, max_length=60, description="Formula, e.g. 'SrTiO3'.")


class GetCandidateArgs(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=20, description="e.g. 'LL-0001'.")


def candidate_summary(candidate: Candidate) -> dict[str, Any]:
    """Compact view of a candidate for the model (the full record has the CIF and all sites)."""
    t = candidate.transformation
    return {
        "candidate_id": candidate.candidate_id,
        "parent_id": candidate.parent_id,
        "formula": candidate.formula,
        "host": t.host.model_dump(exclude_none=True),
        "substitutions": [s.model_dump() for s in t.substitutions],
        "supercell": t.supercell,
        "substituted_sites": t.substituted_sites,
        "assessment_status": candidate.assessment.status,
        "checks": [
            {"id": c.id, "status": c.status, "message": c.message}
            for c in candidate.assessment.checks
            if c.status != "not_applicable"
        ],
        "notes": candidate.assessment.notes,
        "refractive_index_estimate": (
            candidate.optical_estimate.model_dump(exclude_none=True)
            if candidate.optical_estimate
            else None
        ),
        "experiments": [
            e.model_dump(exclude={"created_at"}, exclude_none=True) for e in candidate.experiments
        ],
        "researcher_decisions": [
            {"decision": d.decision, "reason": d.reason} for d in candidate.decisions
        ],
    }


def build_registry(
    mp: MaterialsProjectClient | None,
    literature: LiteratureSearch,
    store: CandidateStore | None = None,
) -> ToolRegistry:
    store = store or get_store()

    def search_materials(args: SearchMaterialsArgs) -> dict[str, Any]:
        if mp is None:
            raise ToolError(
                "Materials Project is not configured (MP_API_KEY missing). "
                "Report material properties as unknown."
            )
        records = mp.search(
            formula=args.formula,
            elements=args.elements,
            band_gap_min=args.band_gap_min,
            limit=args.limit,
        )
        return {
            "count": len(records),
            "results": [r.model_dump(exclude_none=True) for r in records],
        }

    def search_literature(args: SearchLiteratureArgs) -> dict[str, Any]:
        result = literature.search(args.query, limit=args.limit)
        return {
            "count": len(result.papers),
            "results": [p.model_dump(exclude_none=True) for p in result.papers],
            "source_status": result.source_status,
        }

    def new_candidate(args: CreateCandidateArgs) -> dict[str, Any]:
        host, host_ref, parent_id = load_host(
            store, mp, material_id=args.host_material_id, candidate_id=args.host_candidate_id
        )
        candidate = create_candidate(store, host, host_ref, args.substitutions, parent_id, mp)
        return candidate_summary(candidate)

    def optical_reference(args: OpticalReferenceArgs) -> dict[str, Any]:
        ref = get_reference_db().reference(args.formula)
        return {
            "formula": ref.formula,
            "best_n": ref.best_n.model_dump(exclude_none=True),
            "measured": [
                m.model_dump(exclude={"url"}, exclude_none=True) for m in ref.measured[:6]
            ],
            "computed": [
                c.model_dump(exclude={"url"}, exclude_none=True) for c in ref.computed[:5]
            ],
            "note": ref.note,
        }

    def get_candidate(args: GetCandidateArgs) -> dict[str, Any]:
        stored = store.get(args.candidate_id)
        if stored is None:
            raise ToolError(f"No candidate {args.candidate_id}.")
        return candidate_summary(stored[0])

    return ToolRegistry(
        [
            COMPOSITION_TOOL,
            Tool(
                name="create_candidate",
                description=(
                    "Make a candidate material by replacing a fraction of one element's sites in "
                    "a known host structure (or an earlier candidate), then run structural checks: "
                    "charge balance, distances, ionic size fit, coordination, bond valence sum, "
                    "tolerance factor, and known analogs. Atoms are not relaxed."
                ),
                args_model=CreateCandidateArgs,
                handler=new_candidate,
            ),
            Tool(
                name="get_candidate",
                description=(
                    "Read an existing candidate: its host, substitutions, structural checks, "
                    "and the researcher's decisions and reasons."
                ),
                args_model=GetCandidateArgs,
                handler=get_candidate,
            ),
            Tool(
                name="get_optical_reference",
                description=(
                    "Refractive index evidence for a formula: measured n at 450/550/650 nm "
                    "(refractiveindex.info, with sources) and DFT band gaps and n from JARVIS-DFT "
                    "(OptB88vdW and TBmBJ). Matched by formula, so the polymorph can differ."
                ),
                args_model=OpticalReferenceArgs,
                handler=optical_reference,
            ),
            Tool(
                name="search_materials",
                description=(
                    "Search the Materials Project database for known crystalline materials. "
                    "Returns IDs, formulas, symmetry, and DFT-computed band gap, energy above "
                    "hull, and refractive index, each with an evidence status and source."
                ),
                args_model=SearchMaterialsArgs,
                handler=search_materials,
            ),
            Tool(
                name="search_literature",
                description=(
                    "Search OpenAlex, Crossref, arXiv, and Semantic Scholar for papers (merged by DOI). "
                    "Returns titles, authors, year, venue, DOI, open-access links, and which "
                    "sources found each paper. Only metadata, not full text."
                ),
                args_model=SearchLiteratureArgs,
                handler=search_literature,
            ),
        ]
    )
