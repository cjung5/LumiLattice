"""Read-only lookups in the bundled reference database (backend/data/reference.sqlite).

Built by scripts/build_reference_db.py from JARVIS-DFT (CC BY 4.0), the refractiveindex.info
database (CC0), and the Zhuo et al. band-gap compilation (MIT). Data is matched by reduced formula, so the
polymorph can differ from the selected structure; every value says so.
"""

import json
import math
import sqlite3
import statistics
import threading
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

import numpy as np
from pymatgen.core import Composition
from scipy.optimize import nnls

from app.config import get_settings
from app.models.evidence import PropertyValue, Provenance
from app.models.optical import (
    ComputedOptics,
    DispersionCurve,
    DispersionData,
    EndMemberIndex,
    Landscape,
    LandscapePoint,
    LinearMix,
    MeasuredIndex,
    OpticalEstimate,
    OpticalReference,
)
from app.tools.registry import ToolError

# Measured pages that describe the bulk material (thin films and nanoparticles differ).
BULK_CATEGORIES = {"bulk", "crystal", ""}
MATCH_NOTE = "Matched by formula; the polymorph may differ from the selected structure."
# Added to both ends of a Heuristic range, from scripts/validate_score.py. Gap: on hand-checked
# oxide solid solutions, coverage stops rising at 0.3 eV (86% inside, also 86% at 0.5 eV). n: 91%
# of computed wide-gap oxide mixes fall inside at 0.2, but only 12 measured mixes exist, not reviewed.
GAP_MARGIN_EV = 0.3
N_MARGIN = 0.2
# Median error of a linear mix on tested oxides (scripts/validate_score.py): 43 hand-checked band
# gaps and 12 unreviewed n values. tests/test_validate_score.py keeps these in step with the report.
MIX_TYPICAL_GAP_ERROR_EV = 0.6
MIX_TYPICAL_N_ERROR = 0.3
MIX_TOLERANCE = 1e-3
MIX_NOTE = (
    "End-member values weighted by each one's share of the composition. A guide, not a prediction: "
    "real mixes can bend away from a straight line. Verdicts and the score use the range."
)
N_NOTE = f"Widened by {N_MARGIN} on each side, from tests on computed mixes."
GAP_NOTE_RANGE = (
    f"Widened by {GAP_MARGIN_EV} eV on each side, from tests on measured oxide solid solutions."
)
# scripts/validate_score.py: within this spread (middle half of the reports) the median is far
# closer to compiled measured gaps than TBmBJ is. Beyond it, reports disagree (SiO2: 3.2-9.0 eV).
MAX_MINED_SPREAD_EV = 1.0
MINED_NOTE = (
    "Text mining makes errors, and the papers can report films, nanoparticles, or doped samples."
)
GAP_NOTE = "Reported in the literature; the compilation does not record the measurement method."
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
        self._local = threading.local()

    @property
    def _db(self) -> sqlite3.Connection | None:
        """This thread's connection. API requests run in parallel threads, which must not share one."""
        if not self.available:
            return None
        if not hasattr(self._local, "db"):
            self._local.db = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        return self._local.db

    def meta(self) -> dict[str, str]:
        """Build metadata: dataset versions, licenses, and SHA-256 of the downloaded files."""
        if self._db is None:
            return {}
        return dict(self._db.execute("SELECT key, value FROM meta").fetchall())

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
            best_gap=self.best_gap(formula),
            measured_gaps=self.measured_gaps(formula),
            measured=self.measured(formula),
            computed=self.computed(formula),
            note=MATCH_NOTE if self.available else "Reference database is not built.",
        )

    def nearest_known(self, formula: str, count: int = 3) -> list[tuple[str, float]]:
        """Closest known compositions, as the share of atoms that differ (0 = the same)."""
        if self._db is None:
            return []
        target = Composition(formula).fractional_composition.as_dict()
        scored = []
        for known, text in self._db.execute("SELECT formula, fractions FROM known_compositions"):
            fractions = json.loads(text)
            if target.keys().isdisjoint(fractions):
                continue
            distance = sum(abs(target.get(e, 0) - fractions.get(e, 0)) for e in target | fractions)
            scored.append((round(distance / 2, 3), known))
        return [(known, distance) for distance, known in sorted(scored)[:count]]

    def measured_gaps(self, formula: str) -> list[float]:
        if self._db is None:
            return []
        rows = self._db.execute(
            "SELECT gap FROM expt_gaps WHERE formula = ? ORDER BY gap", (formula,)
        ).fetchall()
        return [r[0] for r in rows]

    def mined_gap(self, formula: str) -> tuple[float, float, float, int] | None:
        if self._db is None:
            return None
        return self._db.execute(
            "SELECT median, q1, q3, reports FROM mined_gaps WHERE formula = ?", (formula,)
        ).fetchone()

    def best_gap(self, formula: str) -> PropertyValue:
        """Compiled measured gap, then text-mined measured gap, then JARVIS TBmBJ, then OptB88vdW."""
        measured = self.measured_gaps(formula)
        if measured:
            spread = (
                f"Median of {len(measured)} reports ({measured[0]}–{measured[-1]} eV). "
                if len(measured) > 1
                else ""
            )
            return PropertyValue(
                name="band_gap",
                value=_round(statistics.median(measured)),
                units="eV",
                status="Experimental",
                conditions=f"{spread}{GAP_NOTE} {MATCH_NOTE}",
                provenance=Provenance(
                    source="Zhuo et al. 2018", method="literature compilation", reference=formula
                ),
            )
        mined = self.mined_gap(formula)
        if mined and mined[2] - mined[1] <= MAX_MINED_SPREAD_EV:
            median, q1, q3, reports = mined
            return PropertyValue(
                name="band_gap",
                value=_round(median),
                units="eV",
                status="Experimental",
                conditions=(
                    f"Median of {reports} values text-mined from papers (middle half {q1}–{q3} "
                    f"eV). {MINED_NOTE} {MATCH_NOTE}"
                ),
                provenance=Provenance(
                    source="Dong & Cole 2022", method="text-mined literature", reference=formula
                ),
            )
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

    def estimate(self, end_members: list[str], exact: str | None = None) -> OpticalEstimate:
        """Ranges spanned by the end members' best n and band gap (each needs two values).

        Good data for the exact formula is better evidence than a range: replacing all the Sr in
        SrTiO3 with Ba gives BaTiO3, not something between it and SrTiO3. OptB88vdW values do not
        qualify: its gaps are too low to replace a range from measured end members.
        """
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
        note = f"{note}, and it can mix measured and DFT values."
        n = self.best_n(exact) if exact else None
        gap = self.best_gap(exact) if exact else None
        mix = _linear_mix(members, exact, _good(n), _good(gap))
        return OpticalEstimate(
            linear_mix=mix,
            estimate=n
            if _good(n)
            else _range(
                "refractive_index", n_values, None, f"{note} {N_NOTE}", names, N_MARGIN, 1.0
            ),
            band_gap=gap
            if _good(gap)
            else _range(
                "band_gap", gap_values, "eV", f"{note} {GAP_NOTE_RANGE}", names, GAP_MARGIN_EV, 0.0
            ),
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
                # Measured gap, or TBmBJ. OptB88vdW gaps are too low to plot beside them.
                if (
                    n.status == "Experimental"
                    and gap.value is not None
                    and (gap.status == "Experimental" or gap.provenance.method == "TBmBJ")
                ):
                    measured.append(
                        LandscapePoint(
                            formula=formula,
                            n=n.value,
                            band_gap=gap.value,
                            gap_measured=gap.status == "Experimental",
                        )
                    )
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
                (
                    "Measured: refractiveindex.info bulk n at 550 nm, with a measured band gap "
                    "(Zhuo et al. 2018 or Dong & Cole 2022) or, as an open ring, the JARVIS TBmBJ band gap."
                ),
                (
                    "Computed: JARVIS TBmBJ gap and n = sqrt(eps), a long-wavelength value "
                    f"(an evenly spaced sample of {total} entries)."
                ),
                "Moss relation (n^4 * Eg = 95 eV) is an empirical trend, not a limit.",
            ],
        )


def _range(
    name: str,
    values: list[float],
    units: str | None,
    conditions: str,
    names: str,
    margin: float,
    floor: float,
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
        value_range=(
            round(max(min(values) - margin, floor), 3),
            round(max(values) + margin, 3),
        ),
        units=units,
        status="Heuristic",
        conditions=conditions,
        provenance=Provenance(source="LumiLattice", method="end-member range"),
    )


def mix_shares(formula: str, ends: list[str]) -> dict[str, float] | None:
    """Each end member's share of `formula`, or None if it is not a mix of them.

    Sr3LaTi3AlO12 is 3/4 SrTiO3 and 1/4 LaAlO3. Sr→La 1/4 with Ti→Al 1/2 lies off that line.
    """
    try:
        target = Composition(formula).fractional_composition.as_dict()
        parts = [Composition(end).fractional_composition.as_dict() for end in ends]
    except (ValueError, KeyError):
        return None
    elements = sorted(set(target).union(*parts))
    # The heavily weighted last row makes the shares sum to 1.
    a = np.array([[p.get(e, 0.0) for p in parts] for e in elements] + [[100.0] * len(parts)])
    b = np.array([target.get(e, 0.0) for e in elements] + [100.0])
    shares, _ = nnls(a, b)
    if np.abs(a[:-1] @ shares - b[:-1]).max() > MIX_TOLERANCE:
        return None
    found = {end: round(float(s), 4) for end, s in zip(ends, shares, strict=True) if s > 1e-4}
    return found if len(found) > 1 else None


def _linear_mix(
    members: list[EndMemberIndex], exact: str | None, n_is_exact: bool, gap_is_exact: bool
) -> LinearMix | None:
    """Only for what is still a range: exact-formula values are better evidence than a guess."""
    if exact is None or (n_is_exact and gap_is_exact):
        return None
    shares = mix_shares(exact, [m.formula for m in members])
    if shares is None:
        return None
    used = [m for m in members if m.formula in shares]

    def blend(values: list[float | None]) -> float | None:
        if any(v is None for v in values):
            return None
        return _round(sum(v * shares[m.formula] for v, m in zip(values, used, strict=True)))

    n = None if n_is_exact else blend([m.n.value for m in used])
    gap = None if gap_is_exact else blend([m.band_gap.value if m.band_gap else None for m in used])
    if n is None and gap is None:
        return None
    return LinearMix(
        shares=shares,
        n=n,
        band_gap=gap,
        typical_n_error=MIX_TYPICAL_N_ERROR,
        typical_gap_error_ev=MIX_TYPICAL_GAP_ERROR_EV,
        note=MIX_NOTE,
    )


def _good(pv: PropertyValue | None) -> bool:
    if pv is None or pv.status == "Unknown":
        return False
    return pv.status == "Experimental" or pv.provenance.method == "TBmBJ"


def _round(value: float | None, digits: int = 3) -> float | None:
    return None if value is None else round(value, digits)


@lru_cache
def get_landscape() -> Landscape:
    return get_reference_db().landscape()


@lru_cache
def get_reference_db() -> ReferenceDB:
    return ReferenceDB(get_settings().reference_db_path)
