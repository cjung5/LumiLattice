"""The set of tools the research agent can call."""

from typing import Any

from pydantic import BaseModel, Field

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


def build_registry(mp: MaterialsProjectClient | None, literature: OpenAlexClient) -> ToolRegistry:
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

    return ToolRegistry(
        [
            COMPOSITION_TOOL,
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
