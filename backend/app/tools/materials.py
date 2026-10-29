"""Materials Project adapter (REST API, CC BY 4.0 data).

https://api.materialsproject.org/docs — summary documents include structure, band gap,
energy above hull, and (for a subset) the electronic dielectric constant and n.
"""

import re
from typing import Any

import httpx
from pymatgen.core import Structure

from app.models.evidence import PropertyValue, Provenance
from app.models.materials import MaterialRecord
from app.tools.registry import ToolError, UpstreamError
from app.tools.usage import MP_CACHE, MP_CAP, DailyCap, ResponseCache, cache_key

MP_API_URL = "https://api.materialsproject.org"
MP_WEB_URL = "https://next-gen.materialsproject.org/materials"
# Legacy IDs (mp-5229) and the newer AlphaID form (mp-aaaaahtd) are both accepted.
MATERIAL_ID = re.compile(r"^(mp|mvc)-([0-9]+|[a-z]+)$")
SUMMARY_FIELDS = (
    "material_id,formula_pretty,symmetry,nsites,band_gap,is_metal,energy_above_hull,"
    "is_stable,theoretical,n,e_electronic,database_IDs"
)
DFT_METHOD = "DFT (Materials Project; mostly GGA/GGA+U)"


class MaterialsProjectClient:
    def __init__(
        self,
        api_key: str,
        transport: httpx.BaseTransport | None = None,
        cache: ResponseCache = MP_CACHE,
        cap: DailyCap = MP_CAP,
    ):
        self._http = httpx.Client(
            base_url=MP_API_URL,
            headers={"X-API-KEY": api_key},
            timeout=30,
            transport=transport,
        )
        self._cache = cache
        self._cap = cap

    def close(self) -> None:
        self._http.close()

    def _get(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        # Legacy IDs (mp-5229) match the Materials Project website and most papers.
        params = {**params, "id_format": "legacy"}
        key = cache_key(path, params)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        self._cap.take()
        try:
            response = self._http.get(path, params=params)
        except httpx.HTTPError as exc:
            raise UpstreamError(f"Materials Project request failed: {exc}") from exc
        if response.status_code in (401, 403):
            raise UpstreamError("Materials Project rejected the API key.")
        if response.status_code >= 400:
            raise UpstreamError(
                f"Materials Project error {response.status_code}: {response.text[:200]}"
            )
        data = response.json().get("data", [])
        self._cache.put(key, data)
        return data

    def search(
        self,
        *,
        formula: str | None = None,
        elements: list[str] | None = None,
        material_ids: list[str] | None = None,
        band_gap_min: float | None = None,
        limit: int = 10,
    ) -> list[MaterialRecord]:
        if not (formula or elements or material_ids):
            raise ToolError("Give a formula, elements, or material IDs to search.")
        params: dict[str, Any] = {
            "_fields": SUMMARY_FIELDS,
            "_limit": limit,
            "deprecated": "false",
            "_sort_fields": "energy_above_hull",
        }
        if formula:
            params["formula"] = formula
        if elements:
            params["elements"] = ",".join(elements)
        if material_ids:
            params["material_ids"] = ",".join(material_ids)
        if band_gap_min is not None:
            params["band_gap_min"] = band_gap_min
        return [to_record(doc) for doc in self._get("/materials/summary/", params)]

    def get_structure(self, material_id: str) -> Structure:
        if not MATERIAL_ID.match(material_id):
            raise ToolError(f"{material_id!r} is not a Materials Project ID (e.g. mp-5229).")
        docs = self._get(
            "/materials/summary/",
            {"material_ids": material_id, "_fields": "material_id,structure", "_limit": 1},
        )
        if not docs:
            raise ToolError(f"Materials Project has no material {material_id}.")
        return Structure.from_dict(docs[0]["structure"])


def to_record(doc: dict[str, Any]) -> MaterialRecord:
    material_id = str(doc["material_id"])
    symmetry = doc.get("symmetry") or {}
    provenance = Provenance(source="Materials Project", method=DFT_METHOD, reference=material_id)

    n = doc.get("n")
    if n is not None:
        refractive_index = PropertyValue(
            name="refractive_index",
            value=round(n, 3),
            status="DFT-computed",
            conditions="n = sqrt(eps_electronic): long-wavelength limit, not n(550 nm)",
            provenance=provenance,
        )
    else:
        refractive_index = PropertyValue(name="refractive_index", status="Unknown")

    band_gap = doc.get("band_gap")
    e_hull = doc.get("energy_above_hull")
    return MaterialRecord(
        material_id=material_id,
        formula=doc.get("formula_pretty") or "",
        crystal_system=symmetry.get("crystal_system"),
        spacegroup=symmetry.get("symbol"),
        spacegroup_number=symmetry.get("number"),
        nsites=doc.get("nsites"),
        is_stable=bool(doc.get("is_stable")),
        theoretical=bool(doc.get("theoretical", True)),
        icsd_ids=[str(i) for i in (doc.get("database_IDs") or {}).get("icsd", [])],
        band_gap=PropertyValue(
            name="band_gap",
            value=None if band_gap is None else round(band_gap, 3),
            units="eV",
            status="Unknown" if band_gap is None else "DFT-computed",
            conditions="DFT band gaps are usually lower than measured gaps",
            provenance=provenance,
        ),
        energy_above_hull=PropertyValue(
            name="energy_above_hull",
            value=None if e_hull is None else round(e_hull, 4),
            units="eV/atom",
            status="Unknown" if e_hull is None else "DFT-computed",
            conditions="thermodynamic stability at 0 K; not a synthesis prediction",
            provenance=provenance,
        ),
        refractive_index=refractive_index,
        url=f"{MP_WEB_URL}/{material_id}",
    )


def parse_query(query: str) -> dict[str, Any]:
    """Map one search box string to MP filters: an ID, an element list, or a formula."""
    query = query.strip()
    if MATERIAL_ID.match(query):
        return {"material_ids": [query]}
    if "," in query:
        return {"elements": [e.strip() for e in query.split(",") if e.strip()]}
    return {"formula": query}
