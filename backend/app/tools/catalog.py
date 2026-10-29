"""The set of tools the research agent can call."""

from typing import Any

from pydantic import BaseModel, Field

from app.models.candidates import Substitution
from app.storage.memory import STORE, CandidateStore
from app.tools.candidates import create_candidate, load_host
from app.tools.composition import COMPOSITION_TOOL
from app.tools.literature import OpenAlexClient
from app.tools.materials import MaterialsProjectClient
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


def build_registry(
    mp: MaterialsProjectClient | None,
    literature: OpenAlexClient,
    store: CandidateStore = STORE,
) -> ToolRegistry:
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
        papers = literature.search(args.query, limit=args.limit)
        return {"count": len(papers), "results": [p.model_dump(exclude_none=True) for p in papers]}

    def new_candidate(args: CreateCandidateArgs) -> dict[str, Any]:
        host, host_ref, parent_id = load_host(
            store, mp, material_id=args.host_material_id, candidate_id=args.host_candidate_id
        )
        candidate = create_candidate(store, host, host_ref, args.substitutions, parent_id, mp)
        assessment = candidate.assessment
        return {
            "candidate_id": candidate.candidate_id,
            "parent_id": candidate.parent_id,
            "formula": candidate.formula,
            "supercell": candidate.transformation.supercell,
            "substituted_sites": candidate.transformation.substituted_sites,
            "assessment_status": assessment.status,
            "checks": [
                {"id": c.id, "status": c.status, "message": c.message}
                for c in assessment.checks
                if c.status != "not_applicable"
            ],
            "notes": assessment.notes,
        }

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
                    "Search OpenAlex for scientific papers. Returns titles, authors, year, "
                    "venue, DOI, and open-access status. Only metadata, not full text."
                ),
                args_model=SearchLiteratureArgs,
                handler=search_literature,
            ),
        ]
    )
