"""Read-only lookups in the bundled reference database (backend/data/reference.sqlite).

Built by scripts/build_reference_db.py from JARVIS-DFT (CC BY 4.0) and the
refractiveindex.info database (CC0). Data is matched by reduced formula, so the
polymorph can differ from the selected structure; every value says so.
"""

import json
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
    DispersionCurve,
    DispersionData,
    EndMemberIndex,
    Landscape,
    LandscapePoint,
    MeasuredIndex,
    OpticalEstimate,
    OpticalReference,
)
from app.tools.registry import ToolError

# Measured pages that describe the bulk material (thin films and nanoparticles differ).
BULK_CATEGORIES = {"bulk", "crystal", ""}
MATCH_NOTE = "Matched by formula; the polymorph may differ from the selected structure."
CURVE_NM = list(range(380, 781, 10))
LANDSCAPE_SAMPLE = 2500
MOSS_CONSTANT_EV = 95.0  # empirical Moss relation, n^4 * Eg ≈ 95 eV
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

    def best_gap(self, formula: str) -> PropertyValue:
        """JARVIS TBmBJ band gap (closer to measured), else OptB88vdW; median over ICSD entries."""
        computed = self.computed(formula)
        for field, method, note in (
            ("band_gap_mbj", "TBmBJ", "TBmBJ gaps are usually close to measured gaps"),
            ("band_gap_optb88vdw", "OptB88vdW", "OptB88vdW (GGA-type) gaps are usually too small"),
        ):
            icsd = [
                getattr(c, field) for c in computed if c.has_icsd and getattr(c, field) is not None
            ]
            values = icsd or [getattr(c, field) for c in computed if getattr(c, field) is not None]
            if values:
                return PropertyValue(
                    name="band_gap",
                    value=_round(statistics.median(values)),
                    units="eV",
                    status="DFT-computed",
                    conditions=f"{note}. {MATCH_NOTE}",
                    provenance=Provenance(source="JARVIS-DFT", method=method, reference=formula),
                )
        return PropertyValue(name="band_gap", units="eV", status="Unknown", conditions=MATCH_NOTE)

    def estimate(self, end_members: list[str]) -> OpticalEstimate:
        """Ranges spanned by the end members' best n and band gap (each needs two values)."""
        members = [
            EndMemberIndex(formula=f, n=self.best_n(f), band_gap=self.best_gap(f))
            for f in dict.fromkeys(end_members)
        ]
        names = ", ".join(m.formula for m in members)
        note = (
            f"Range spanned by end members {names}. Not a prediction: it assumes the value "
            "lies between them"
        )
        n_values = [m.n.value for m in members if m.n.value is not None]
        gap_values = [
            m.band_gap.value for m in members if m.band_gap and m.band_gap.value is not None
        ]
        return OpticalEstimate(
            estimate=_range(
                "refractive_index",
                n_values,
                None,
                f"{note}, and it can mix measured and DFT values.",
                names,
            ),
            band_gap=_range("band_gap", gap_values, "eV", f"{note}. Gaps are DFT (JARVIS).", names),
            end_members=members,
        )

    def dispersion(self, formula: str) -> DispersionData:
        formula = normalize(formula)
        rows = (
            self._db.execute(
                "SELECT title, category, direction, curve FROM ri_pages WHERE formula = ? "
                "ORDER BY category, page",
                (formula,),
            ).fetchall()
            if self._db
            else []
        )
        curves = [
            DispersionCurve(title=r[0], category=r[1], direction=r[2], n=json.loads(r[3]))
            for r in rows
            if r[3]
        ]
        bulk = [c.n for c in curves if c.category.lower() in BULK_CATEGORIES]
        median = None
        if bulk:
            median = [
                _round(statistics.median(vals))
                if (vals := [c[i] for c in bulk if c[i] is not None])
                else None
                for i in range(len(CURVE_NM))
            ]
        return DispersionData(
            formula=formula, wavelengths_nm=CURVE_NM, curves=curves, bulk_median=median
        )

    def landscape(self) -> Landscape:
        measured: list[LandscapePoint] = []
        computed: list[tuple[float, float]] = []
        total = 0
        if self._db is not None:
            formulas = [r[0] for r in self._db.execute("SELECT DISTINCT formula FROM ri_pages")]
            for formula in formulas:
                n, gap = self.best_n(formula), self.best_gap(formula)
                if (
                    n.status == "Experimental"
                    and gap.value is not None
                    and gap.provenance.method == "TBmBJ"
                ):
                    measured.append(LandscapePoint(formula=formula, n=n.value, band_gap=gap.value))
            rows = self._db.execute(
                "SELECT mbj_gap, eps_mbj FROM jarvis WHERE mbj_gap > 0 AND eps_mbj >= 1 ORDER BY jid"
            ).fetchall()
            total = len(rows)
            step = max(1, math.ceil(total / LANDSCAPE_SAMPLE))
            computed = [(round(g, 3), round(math.sqrt(e), 3)) for g, e in rows[::step]]
        moss = [(g / 10, round((MOSS_CONSTANT_EV / (g / 10)) ** 0.25, 3)) for g in range(5, 101, 5)]
        return Landscape(
            measured=sorted(measured, key=lambda p: p.formula),
            computed=computed,
            computed_total=total,
            moss=moss,
            notes=[
                "Measured: refractiveindex.info bulk n at 550 nm, with the JARVIS TBmBJ band gap.",
                (
                    "Computed: JARVIS TBmBJ gap and n = sqrt(eps), a long-wavelength value "
                    f"(an evenly spaced sample of {total} entries)."
                ),
                "Moss relation (n^4 * Eg = 95 eV) is an empirical trend, not a limit.",
            ],
        )


def _range(
    name: str, values: list[float], units: str | None, conditions: str, names: str
) -> PropertyValue:
    if len(values) < 2:
        return PropertyValue(
            name=name,
            units=units,
            status="Unknown",
            conditions=f"Not enough end-member data ({names}) for a range.",
        )
    return PropertyValue(
        name=name,
        value_range=(min(values), max(values)),
        units=units,
        status="Heuristic",
        conditions=conditions,
        provenance=Provenance(source="LumiLattice", method="end-member range"),
    )


def _round(value: float | None, digits: int = 3) -> float | None:
    return None if value is None else round(value, digits)


@lru_cache
def get_landscape() -> Landscape:
    return get_reference_db().landscape()


@lru_cache
def get_reference_db() -> ReferenceDB:
    return ReferenceDB(get_settings().reference_db_path)
