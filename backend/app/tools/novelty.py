"""How new is a candidate? Exact matches and related work in the sources this app can reach.

"Not found" is a statement about these sources only. Patents, papers that write the composition
another way, and unpublished work are not checked, so the app never calls a candidate a discovery.
"""

import re
from typing import Literal

from pydantic import BaseModel
from pymatgen.core import Composition

from app.models.candidates import Candidate
from app.models.materials import PaperEvidence
from app.tools.candidates import solid_solution_ends
from app.tools.cod import CodClient
from app.tools.literature_sources import LiteratureSearch
from app.tools.materials import MaterialsProjectClient
from app.tools.reference_db import ReferenceDB
from app.tools.registry import ToolError

# Most known first: the level is the first one with evidence.
NoveltyLevel = Literal["known", "computed", "related", "unreported"]
CheckId = Literal["mp_exact", "cod_exact", "reference", "mp_system", "papers"]
CAVEAT = (
    "This checks Materials Project, COD, the bundled reference data, and paper titles from "
    "OpenAlex, Crossref, arXiv, and Semantic Scholar. It cannot check patents, unpublished work, "
    "or papers that write the composition another way. Not found does not mean new."
)
MAX_ITEMS = 5


class NoveltyLink(BaseModel):
    label: str
    url: str | None = None


class NoveltyCheck(BaseModel):
    id: CheckId
    status: Literal["found", "not_found", "unavailable"]
    detail: str
    items: list[NoveltyLink] = []


class NearestKnown(BaseModel):
    formula: str
    atoms_differ: float  # share of atoms that differ, 0 to 1


class Novelty(BaseModel):
    subject: str
    formula: str
    level: NoveltyLevel
    complete: bool  # False: at least one source could not be reached
    checks: list[NoveltyCheck]
    nearest: list[NearestKnown]
    caveat: str = CAVEAT


def _flat(title: str) -> str:
    """Titles write formulas with tags and subscripts: SrTiO<sub>3</sub>, SrTiO₃."""
    title = re.sub(r"<[^>]+>", "", title).translate(str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789"))
    return re.sub(r"\s+", " ", title)


def names_candidate(title: str, candidate: Candidate, ends: list[str]) -> bool:
    """The title names the formula, every end member, or the host and every new element."""
    text = _flat(title)
    if candidate.formula in text or (len(ends) > 1 and all(end in text for end in ends)):
        return True
    t = candidate.transformation
    new = {s.element_to for s in t.lineage}
    # "Al" must not match "Alloy", and "La" must not match "Lattice".
    return t.root_formula in text and all(re.search(rf"{el}(?![a-z])", text) for el in new)


def paper_query(candidate: Candidate, ends: list[str]) -> str:
    if len(ends) > 1:
        return f"{' '.join(ends)} solid solution"
    new = " ".join(sorted({s.element_to for s in candidate.transformation.lineage}))
    return f"{new} doped {candidate.transformation.root_formula}"


def _paper_link(paper: PaperEvidence) -> NoveltyLink:
    year = f" ({paper.year})" if paper.year else ""
    url = paper.url or (f"https://doi.org/{paper.doi}" if paper.doi else None)
    return NoveltyLink(label=f"{_flat(paper.title)}{year}", url=url)


def check_novelty(
    candidate: Candidate,
    mp: MaterialsProjectClient | None,
    cod: CodClient,
    literature: LiteratureSearch,
    db: ReferenceDB,
) -> Novelty:
    formula = candidate.formula
    t = candidate.transformation
    checks: list[NoveltyCheck] = []
    observed = computed = related = False

    if mp is None:
        checks.append(
            NoveltyCheck(id="mp_exact", status="unavailable", detail="MP_API_KEY is not set.")
        )
        checks.append(
            NoveltyCheck(id="mp_system", status="unavailable", detail="MP_API_KEY is not set.")
        )
    else:
        try:
            records = mp.search(formula=formula, limit=MAX_ITEMS)
            observed |= any(not r.theoretical for r in records)
            computed |= bool(records)
            checks.append(
                NoveltyCheck(
                    id="mp_exact",
                    status="found" if records else "not_found",
                    detail=f"{len(records)} Materials Project entries with this exact formula.",
                    items=[
                        NoveltyLink(
                            label=f"{r.material_id} ({'computed only' if r.theoretical else 'observed'})",
                            url=r.url,
                        )
                        for r in records
                    ],
                )
            )
        except ToolError as exc:
            checks.append(NoveltyCheck(id="mp_exact", status="unavailable", detail=str(exc)))
        try:
            system = "-".join(sorted(el.symbol for el in Composition(formula).elements))
            records = mp.search(chemsys=system, limit=MAX_ITEMS)
            related |= bool(records)
            checks.append(
                NoveltyCheck(
                    id="mp_system",
                    status="found" if records else "not_found",
                    detail=(
                        f"Materials Project entries with exactly the elements {system}: "
                        f"{len(records)}{' or more' if len(records) == MAX_ITEMS else ''}."
                    ),
                    items=[
                        NoveltyLink(label=f"{r.formula} ({r.material_id})", url=r.url)
                        for r in records
                    ],
                )
            )
        except ToolError as exc:
            checks.append(NoveltyCheck(id="mp_system", status="unavailable", detail=str(exc)))

    try:
        entries = cod.search(formula, limit=MAX_ITEMS)
        observed |= bool(entries)
        checks.append(
            NoveltyCheck(
                id="cod_exact",
                status="found" if entries else "not_found",
                detail=f"{len(entries)} measured structures in COD with this exact formula.",
                items=[NoveltyLink(label=f"COD {e.cod_id}", url=e.url) for e in entries],
            )
        )
    except ToolError as exc:
        checks.append(NoveltyCheck(id="cod_exact", status="unavailable", detail=str(exc)))

    measured = bool(db.measured(formula) or db.measured_gaps(formula))
    jarvis = db.computed(formula)
    observed |= measured
    computed |= bool(jarvis)
    checks.append(
        NoveltyCheck(
            id="reference",
            status="found" if measured or jarvis else "not_found",
            detail=(
                f"Reference data for this exact formula: {'measured values' if measured else 'no measured values'}, "
                f"{len(jarvis)} JARVIS-DFT entries."
            ),
        )
    )

    ends = solid_solution_ends(t.root_formula, t.lineage)
    query = paper_query(candidate, ends)
    try:
        result = literature.search(query, limit=MAX_ITEMS)
        if any(status == "ok" for status in result.source_status.values()):
            papers = [p for p in result.papers if names_candidate(p.title, candidate, ends)]
            related |= bool(papers)
            checks.append(
                NoveltyCheck(
                    id="papers",
                    status="found" if papers else "not_found",
                    detail=f'{len(papers)} of {len(result.papers)} papers for "{query}" name this system in the title.',
                    items=[_paper_link(p) for p in papers[:MAX_ITEMS]],
                )
            )
        else:
            checks.append(
                NoveltyCheck(id="papers", status="unavailable", detail="No paper source answered.")
            )
    except ToolError as exc:
        checks.append(NoveltyCheck(id="papers", status="unavailable", detail=str(exc)))

    level: NoveltyLevel = (
        "known" if observed else "computed" if computed else "related" if related else "unreported"
    )
    order = {"mp_exact": 0, "cod_exact": 1, "reference": 2, "mp_system": 3, "papers": 4}
    return Novelty(
        subject=candidate.candidate_id,
        formula=formula,
        level=level,
        complete=all(c.status != "unavailable" for c in checks),
        checks=sorted(checks, key=lambda c: order[c.id]),
        nearest=[NearestKnown(formula=f, atoms_differ=d) for f, d in db.nearest_known(formula)],
    )
