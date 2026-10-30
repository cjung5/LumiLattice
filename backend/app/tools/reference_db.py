"""Read-only lookups in the bundled reference database (backend/data/reference.sqlite).

Built by scripts/build_reference_db.py from JARVIS-DFT (CC BY 4.0) and the
refractiveindex.info database (CC0). Data is matched by reduced formula, so the
polymorph can differ from the selected structure; every value says so.
"""

import math
import sqlite3
import statistics
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from pymatgen.core import Composition

from app.config import get_settings
from app.models.evidence import PropertyValue, Provenance
from app.models.optical import (
    ComputedOptics,
    EndMemberIndex,
    MeasuredIndex,
    OpticalEstimate,
    OpticalReference,
)
from app.tools.registry import ToolError

# Measured pages that describe the bulk material (thin films and nanoparticles differ).
BULK_CATEGORIES = {"bulk", "crystal", ""}
MATCH_NOTE = "Matched by formula; the polymorph may differ from the selected structure."
DFT_N_CONDITIONS = (
    "n = sqrt(eps) from DFT linear optics (electronic, zero frequency): "
    "long-wavelength limit, not n(550 nm)"
)


def normalize(formula: str) -> str:
    try:
        comp = Composition(formula)
    except (ValueError, KeyError) as exc:
        raise ToolError(f"Cannot parse formula {formula!r}.") from exc
    if not comp.valid or comp.num_atoms == 0:
        raise ToolError(f"{formula!r} is not a valid formula.")
    return comp.reduced_formula


class ReferenceDB:
    def __init__(self, path: Path):
        self.path = path
        self.available = path.exists()
        self._db = (
            sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
            if self.available
            else None
        )

    def measured(self, formula: str) -> list[MeasuredIndex]:
        if self._db is None:
            return []
        rows = self._db.execute(
            "SELECT title, category, direction, n_450, n_550, n_650, k_550, wl_min, wl_max, "
            "reference, doi, book, page FROM ri_pages WHERE formula = ? ORDER BY category, page",
            (formula,),
        ).fetchall()
        return [
            MeasuredIndex(
                title=r[0],
                category=r[1],
                direction=r[2],
                n_450=_round(r[3]),
                n_550=_round(r[4]),
                n_650=_round(r[5]),
                k_550=_round(r[6], 4),
                wavelength_range_um=(r[7], r[8]),
                reference=r[9],
                doi=r[10],
                url=f"https://refractiveindex.info/?shelf=main&book={quote(r[11])}&page={quote(r[12])}",
            )
            for r in rows
        ]

    def computed(self, formula: str) -> list[ComputedOptics]:
        if self._db is None:
            return []
        rows = self._db.execute(
            "SELECT jid, mp_id, spg_symbol, has_icsd, optb88vdw_gap, mbj_gap, eps_optb88vdw, "
            "eps_mbj FROM jarvis WHERE formula = ? ORDER BY has_icsd DESC, jid LIMIT 20",
            (formula,),
        ).fetchall()
        return [
            ComputedOptics(
                jid=r[0],
                mp_id=r[1],
                spacegroup=r[2],
                has_icsd=bool(r[3]),
                band_gap_optb88vdw=_round(r[4]),
                band_gap_mbj=_round(r[5]),
                n_optb88vdw=_round(math.sqrt(r[6])) if r[6] else None,
                n_mbj=_round(math.sqrt(r[7])) if r[7] else None,
                url=f"https://www.ctcms.nist.gov/~knc6/static/JARVIS-DFT/{r[0]}.xml",
            )
            for r in rows
        ]

    def best_n(self, formula: str) -> PropertyValue:
        """Measured bulk n(550 nm) first, then JARVIS TBmBJ, then OptB88vdW; else Unknown."""
        bulk = [
            m.n_550
            for m in self.measured(formula)
            if m.n_550 is not None and m.category.lower() in BULK_CATEGORIES
        ]
        if bulk:
            spread = (
                f"; median of {len(bulk)} sources ({min(bulk)}–{max(bulk)}, e.g. o/e directions)"
                if len(bulk) > 1
                else ""
            )
            return PropertyValue(
                name="refractive_index",
                value=_round(statistics.median(bulk)),
                status="Experimental",
                conditions=f"550 nm, bulk{spread}. {MATCH_NOTE}",
                provenance=Provenance(source="refractiveindex.info", reference=formula),
            )
        computed = self.computed(formula)
        for field, method in (("n_mbj", "TBmBJ"), ("n_optb88vdw", "OptB88vdW")):
            values = [getattr(c, field) for c in computed if getattr(c, field) is not None]
            icsd = [getattr(c, field) for c in computed if c.has_icsd and getattr(c, field)]
            values = icsd or values
            if values:
                return PropertyValue(
                    name="refractive_index",
                    value=_round(statistics.median(values)),
                    status="DFT-computed",
                    conditions=f"{DFT_N_CONDITIONS}. {MATCH_NOTE}",
                    provenance=Provenance(source="JARVIS-DFT", method=method, reference=formula),
                )
        return PropertyValue(name="refractive_index", status="Unknown", conditions=MATCH_NOTE)

    def reference(self, formula: str) -> OpticalReference:
        formula = normalize(formula)
        return OpticalReference(
            formula=formula,
            best_n=self.best_n(formula),
            measured=self.measured(formula),
            computed=self.computed(formula),
            note=MATCH_NOTE if self.available else "Reference database is not built.",
        )

    def estimate(self, end_members: list[str]) -> OpticalEstimate:
        """Range spanned by the end members' best n values (needs at least two)."""
        members = [EndMemberIndex(formula=f, n=self.best_n(f)) for f in dict.fromkeys(end_members)]
        values = [m.n.value for m in members if m.n.value is not None]
        names = ", ".join(m.formula for m in members)
        if len(values) < 2:
            estimate = PropertyValue(
                name="refractive_index",
                status="Unknown",
                conditions=f"Not enough end-member data ({names}) for a range.",
            )
        else:
            estimate = PropertyValue(
                name="refractive_index",
                value_range=(min(values), max(values)),
                status="Heuristic",
                conditions=(
                    f"Range spanned by end members {names}. Not a prediction: it assumes the "
                    "value lies between them, and it can mix measured and DFT values."
                ),
                provenance=Provenance(source="LumiLattice", method="end-member range"),
            )
        return OpticalEstimate(estimate=estimate, end_members=members)


def _round(value: float | None, digits: int = 3) -> float | None:
    return None if value is None else round(value, digits)


@lru_cache
def get_reference_db() -> ReferenceDB:
    return ReferenceDB(get_settings().reference_db_path)
