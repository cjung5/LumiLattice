"""Candidate export: CIF files and a JSON research record with provenance.

The CIF is the candidate's P1 cell with a comment header that says where it came from and
what it is (an ordered model, unrelaxed or CHGNet-relaxed). The JSON record holds everything
the app knows about the candidate, plus the goal score, the spatial analysis, the data
versions, and the caveats, so another researcher can check or reproduce it.
"""

from datetime import UTC, datetime
from importlib.metadata import version

from pydantic import BaseModel

from app import __version__
from app.models.candidates import Candidate, Substitution
from app.models.evidence import Provenance
from app.storage.memory import CandidateStore
from app.tools.goals import Goal, GoalScore
from app.tools.scorecard import Scorecard
from app.tools.spatial import SpatialAnalysis

RECORD_FORMAT = "lumilattice.candidate-record/1"
# CIF 1.1 is ASCII; keep common symbols readable in the comment header.
ASCII = str.maketrans({"Å": "A", "→": "->", "×": "x", "–": "-", "—": "-", "°": " deg", "≈": "~"})

EVIDENCE_TAGS = {
    "Experimental": (
        "Measured value: n at 550 nm from bulk or crystal data (refractiveindex.info), or a "
        "literature band gap (Zhuo et al. 2018)."
    ),
    "DFT-computed": (
        "Computed with density functional theory (JARVIS-DFT or Materials Project). "
        "DFT n is a long-wavelength value, not n(550 nm)."
    ),
    "Heuristic": "A range spanned by the candidate's end members. Not a prediction.",
    "Unknown": "No data.",
}

CAVEATS = [
    (
        "The candidate is an ordered supercell model built on the host atom positions. It is not "
        "a measured structure, and one ordered cell is only one model of a disordered solid solution."
    ),
    "Heuristic values are ranges between end members, not predictions.",
    "The scorecard ranks ideas. It is not a probability that the material can be made or will work.",
    (
        "Measured band gaps come from a literature compilation, matched by formula, with no "
        "record of the method or the polymorph."
    ),
    "DFT band gaps (JARVIS TBmBJ, OptB88vdW) can underestimate measured gaps of some oxides.",
    (
        "Structural checks use heuristic thresholds. They do not predict whether the material can "
        "be synthesized."
    ),
    "Ewald ordering energies are unscreened point-charge energies, for ranking only.",
    "CHGNet energies come from a machine-learned potential. Do not compare them with DFT energies.",
]


class Ancestor(BaseModel):
    candidate_id: str
    formula: str
    host: Provenance
    substitutions: list[Substitution]


class DataSource(BaseModel):
    name: str
    used_for: str
    detail: str | None = None
    license: str | None = None
    url: str | None = None


class SpatialRecord(BaseModel):
    unrelaxed: SpatialAnalysis | None = None
    relaxed: SpatialAnalysis | None = None


class CandidateRecord(BaseModel):
    format: str = RECORD_FORMAT
    exported_at: datetime
    software: dict[str, str]
    candidate: Candidate
    ancestry: list[Ancestor]
    goal: Goal | None = None
    goal_score: GoalScore | None = None
    scorecard: Scorecard | None = None
    spatial: SpatialRecord
    data_sources: list[DataSource]
    evidence_tags: dict[str, str]
    caveats: list[str]


def describe(substitutions: list[Substitution]) -> str:
    return ", ".join(f"{s.element_from}->{s.element_to} {s.fraction:.0%}" for s in substitutions)


def ancestry(store: CandidateStore, candidate: Candidate) -> list[Ancestor]:
    """Parents from the nearest to the root; the root's host is the original structure."""
    chain: list[Ancestor] = []
    seen = {candidate.candidate_id}
    parent_id = candidate.parent_id
    while parent_id and parent_id not in seen:
        stored = store.get(parent_id)
        if stored is None:
            break
        parent = stored[0]
        chain.append(
            Ancestor(
                candidate_id=parent.candidate_id,
                formula=parent.formula,
                host=parent.transformation.host,
                substitutions=parent.transformation.substitutions,
            )
        )
        seen.add(parent_id)
        parent_id = parent.parent_id
    return chain


def root_host(candidate: Candidate, chain: list[Ancestor]) -> Provenance:
    return chain[-1].host if chain else candidate.transformation.host


def cif_text(candidate: Candidate, chain: list[Ancestor], relaxed: bool = False) -> str:
    """The P1 CIF with a provenance header (CIF comments, ASCII only)."""
    if relaxed and candidate.relaxation is None:
        raise ValueError(f"{candidate.candidate_id} has not been relaxed.")
    payload = (
        candidate.relaxation.structure if relaxed and candidate.relaxation else candidate.structure
    )
    host = root_host(candidate, chain)
    geometry = (
        f"relaxed with {candidate.relaxation.method}"
        if relaxed and candidate.relaxation
        else "host atom positions, not relaxed"
    )
    lines = [
        f"# LumiLattice candidate {candidate.candidate_id} ({candidate.formula})",
        f"# Original host: {host.source} {host.reference or ''}".rstrip(),
        (
            f"# Substitutions from {candidate.transformation.root_formula}: "
            f"{describe(candidate.transformation.lineage)}"
        ),
        f"# Geometry: {geometry}",
        "# P1 cell: every site is listed, in the same order as the site indices in the app.",
        "# This is an ordered model of a candidate, not a measured structure.",
        f"# Exported {datetime.now(UTC):%Y-%m-%d %H:%M} UTC by LumiLattice {__version__}",
    ]
    header = "\n".join(line.translate(ASCII).encode("ascii", "replace").decode() for line in lines)
    return f"{header}\n{payload.cif}"


def data_sources(
    candidate: Candidate, host: Provenance, reference_meta: dict[str, str]
) -> list[DataSource]:
    sources: list[DataSource] = []
    reference = host.reference or ""
    if host.source == "Materials Project":
        sources.append(
            DataSource(
                name="Materials Project",
                used_for="host structure",
                detail=reference,
                license="CC BY 4.0",
                url=f"https://materialsproject.org/materials/{reference}",
            )
        )
    elif reference.startswith("COD "):
        cod_id = reference.removeprefix("COD ").strip()
        sources.append(
            DataSource(
                name="Crystallography Open Database",
                used_for="host structure",
                detail=reference,
                license="CC0",
                url=f"https://www.crystallography.net/cod/{cod_id}.html",
            )
        )
    else:
        sources.append(
            DataSource(
                name=host.source,
                used_for="host structure",
                detail=reference or None,
                license="as provided by the researcher",
            )
        )
    analogs = next((c for c in candidate.assessment.checks if c.id == "analogs"), None)
    if analogs and analogs.status != "not_applicable" and host.source != "Materials Project":
        sources.append(
            DataSource(
                name="Materials Project",
                used_for="end-member analogs in the structural checks",
                license="CC BY 4.0",
                url="https://materialsproject.org",
            )
        )
    if candidate.optical_estimate:
        datasets = (
            ("jarvis", "JARVIS-DFT", "CC BY 4.0"),
            ("refractiveindex", "refractiveindex.info", "CC0"),
            ("expt_gap", "Zhuo et al. 2018, J. Phys. Chem. Lett. 9, 1668", "MIT"),
            ("mined_gap", "Dong & Cole 2022, Sci. Data 9, 193", "MIT"),
        )
        for key, name, license_ in datasets:
            if key in reference_meta:
                sha = reference_meta.get(f"{key}_sha256")
                sources.append(
                    DataSource(
                        name=name,
                        used_for="refractive index and band gap evidence",
                        detail=reference_meta[key] + (f"; SHA-256 {sha}" if sha else ""),
                        license=license_,
                    )
                )
    if candidate.relaxation:
        sources.append(
            DataSource(
                name="CHGNet",
                used_for="relaxed geometry",
                detail=candidate.relaxation.method,
                license="BSD-3-Clause",
            )
        )
    sources.append(
        DataSource(
            name="pymatgen",
            used_for="structure analysis, Shannon radii, bond-valence parameters, Ewald sums",
            detail=f"version {version('pymatgen')}",
            license="MIT",
        )
    )
    return sources


def build_record(
    store: CandidateStore,
    candidate: Candidate,
    reference_meta: dict[str, str],
    goal: Goal | None,
    goal_score: GoalScore | None,
    spatial: SpatialRecord,
    scorecard: Scorecard | None = None,
) -> CandidateRecord:
    chain = ancestry(store, candidate)
    return CandidateRecord(
        exported_at=datetime.now(UTC),
        software={"lumilattice_api": __version__, "pymatgen": version("pymatgen")},
        candidate=candidate,
        ancestry=chain,
        goal=goal,
        goal_score=goal_score,
        scorecard=scorecard,
        spatial=spatial,
        data_sources=data_sources(candidate, root_host(candidate, chain), reference_meta),
        evidence_tags=EVIDENCE_TAGS,
        caveats=CAVEATS,
    )
