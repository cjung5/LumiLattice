"""Crystallography Open Database: experimental crystal structures (CC0).

https://www.crystallography.net/cod/ — users should acknowledge the original authors of
each structure, so every entry carries its authors, journal, year, and DOI.
"""

import re
from typing import Any

import httpx
from pydantic import BaseModel
from pymatgen.core import Composition

from app.tools.literature_sources import USER_AGENT
from app.tools.reference_db import normalize
from app.tools.registry import ToolError, UpstreamError
from app.tools.usage import COD_CACHE, COD_CAP, DailyCap, ResponseCache

COD_URL = "https://www.crystallography.net/cod"
COD_ID = re.compile(r"^\d{7}$")
MAX_CIF_BYTES = 2_000_000


class CodEntry(BaseModel):
    cod_id: str
    formula: str
    spacegroup: str | None
    spacegroup_number: int | None
    cell: tuple[float | None, float | None, float | None]
    year: int | None
    authors: str | None
    title: str | None
    journal: str | None
    doi: str | None
    url: str


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_entry(row: dict[str, Any]) -> CodEntry:
    cod_id = str(row["file"])
    year = str(row.get("year") or "")
    number = str(row.get("sgNumber") or "")
    return CodEntry(
        cod_id=cod_id,
        formula=str(row.get("formula") or "").strip("- ").strip(),
        spacegroup=(row.get("sg") or "").replace(" ", "") or None,
        spacegroup_number=int(number) if number.isdigit() else None,
        cell=(_float(row.get("a")), _float(row.get("b")), _float(row.get("c"))),
        year=int(year) if year.isdigit() else None,
        authors=row.get("authors"),
        title=row.get("title"),
        journal=row.get("journal"),
        doi=row.get("doi"),
        url=f"{COD_URL}/{cod_id}.html",
    )


class CodClient:
    def __init__(
        self,
        transport: httpx.BaseTransport | None = None,
        cache: ResponseCache = COD_CACHE,
        cap: DailyCap = COD_CAP,
    ):
        self._http = httpx.Client(
            base_url=COD_URL,
            headers={"User-Agent": USER_AGENT},
            timeout=30,
            transport=transport,
            follow_redirects=True,
        )
        self._cache, self._cap = cache, cap

    def close(self) -> None:
        self._http.close()

    def _get(self, path: str, params: dict[str, str] | None = None) -> httpx.Response:
        self._cap.take()
        try:
            response = self._http.get(path, params=params)
        except httpx.HTTPError as exc:
            raise UpstreamError(f"COD request failed: {exc}") from exc
        if response.status_code >= 400:
            raise UpstreamError(f"COD error {response.status_code}")
        return response

    def search(self, formula: str, limit: int = 20) -> list[CodEntry]:
        """Exact formula match; COD stores formulas in Hill notation, e.g. 'O3 Sr Ti'."""
        hill = Composition(normalize(formula)).reduced_composition.hill_formula
        key = f"search:{hill}"
        cached = self._cache.get(key)
        if cached is None:
            cached = [
                to_entry(r)
                for r in self._get("/result", {"formula": hill, "format": "json"}).json()
            ]
            self._cache.put(key, cached)
        return cached[:limit]

    def get_cif(self, cod_id: str) -> str:
        if not COD_ID.match(cod_id):
            raise ToolError(f"{cod_id!r} is not a COD ID (7 digits, e.g. 1512124).")
        key = f"cif:{cod_id}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        text = self._get(f"/{cod_id}.cif").text
        if len(text) > MAX_CIF_BYTES:
            raise ToolError(f"COD {cod_id} CIF is too large.")
        self._cache.put(key, text)
        return text
