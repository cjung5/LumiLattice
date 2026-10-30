"""Spatial (3D) analysis of a structure: symmetry and optical class, coordination polyhedra
and their distortion, polyhedral connectivity and B-X-B angles (octahedral tilts), and
where the substituted ions sit (dopant distances, ordering energies).

All numbers are deterministic geometry or a point-charge Ewald model. They describe the
model structure; an ordered supercell is one model of a disordered solid solution.
"""

import itertools
import math
import random
from collections import defaultdict
from typing import Literal

import numpy as np
from pydantic import BaseModel
from pymatgen.analysis.ewald import EwaldSummation
from pymatgen.analysis.local_env import LocalStructOrderParams
from pymatgen.core import Structure
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from scipy.spatial import ConvexHull

from app.tools.ionic import IonicModel, anion_shell, ionic_model

OpticalClass = Literal["isotropic", "uniaxial", "biaxial"]
OPTICAL_CLASS: dict[str, OpticalClass] = {
    "cubic": "isotropic",
    "tetragonal": "uniaxial",
    "hexagonal": "uniaxial",
    "trigonal": "uniaxial",
    "orthorhombic": "biaxial",
    "monoclinic": "biaxial",
    "triclinic": "biaxial",
}
MAX_ORDERINGS = 300
_ORDER_PARAMS = LocalStructOrderParams(["oct", "tet", "sq_plan"])


class SymmetryInfo(BaseModel):
    spacegroup: str | None
    number: int | None
    crystal_system: str | None
    optical_class: OpticalClass | None


class Polyhedron(BaseModel):
    index: int
    element: str
    coordination: int
    shape: str  # e.g. "octahedron", "tetrahedron", "12-coordinate"
    shape_score: float | None  # pymatgen local order parameter (1 = ideal); CN 4 and 6 only
    distortion_index: float  # Baur (1974): mean |d - d_avg| / d_avg
    quadratic_elongation: float | None  # Robinson et al. (1971), octahedra only
    bond_angle_variance: float | None  # deg^2, octahedra only
    volume: float | None  # Å^3


class Linkages(BaseModel):
    corner: int
    edge: int
    face: int
    # B-X-B angles (degrees) through corner-shared anions between 6-coordinate cations.
    bxb_angles: list[float]
    mean_tilt: float | None  # (180 - angle) / 2, averaged


class DopantArrangement(BaseModel):
    element: str
    sites: list[int]
    nearest_distances: list[float]  # Å, each dopant to its nearest same-element dopant
    shortest: float | None
    cation_spacing: float  # Å, shortest host distance between sites of the replaced element


class OrderingRank(BaseModel):
    """Every way to place the same substitutions in the same supercell, ranked by Ewald energy."""

    energies: list[float]  # meV/atom above the lowest ordering, one per configuration
    chosen: float  # meV/atom above the lowest, for the candidate's own ordering
    chosen_rank: int  # 1 = lowest among distinct energies
    distinct: int
    total: int
    truncated: bool
    analysis_cell: tuple[int, int, int]  # repeat of the candidate cell used for the ranking
    method: str


class SpatialAnalysis(BaseModel):
    symmetry: SymmetryInfo
    parent_symmetry: SymmetryInfo | None = None
    polyhedra: list[Polyhedron]
    linkages: Linkages
    # The same sites and framework before this substitution step (for before/after charts).
    parent_polyhedra: list[Polyhedron] = []
    parent_linkages: Linkages | None = None
    dopants: list[DopantArrangement] = []
    ordering: OrderingRank | None = None
    findings: list[str]
    notes: list[str]


def symmetry_of(structure: Structure) -> SymmetryInfo:
    try:
        spg = SpacegroupAnalyzer(structure, symprec=0.1)
        system = spg.get_crystal_system()
        return SymmetryInfo(
            spacegroup=spg.get_space_group_symbol(),
            number=spg.get_space_group_number(),
            crystal_system=system,
            optical_class=OPTICAL_CLASS.get(system),
        )
    except ValueError:
        return SymmetryInfo(spacegroup=None, number=None, crystal_system=None, optical_class=None)


def polyhedron(structure: Structure, index: int, model: IonicModel) -> Polyhedron | None:
    shell = anion_shell(structure, index, model)
    if len(shell) < 3:
        return None
    center = structure[index].coords
    vectors = np.array([n.coords - center for n in shell])
    lengths = np.linalg.norm(vectors, axis=1)
    mean = float(lengths.mean())
    cn = len(shell)

    shape, score = f"{cn}-coordinate", None
    params = _ORDER_PARAMS.get_order_parameters(
        structure, index, indices_neighs=[n.index for n in shell]
    )
    if cn == 6 and params[0] is not None:
        shape, score = "octahedron", params[0]
    elif cn == 4 and None not in params[1:]:
        shape, score = (
            ("tetrahedron", params[1]) if params[1] >= params[2] else ("square plane", params[2])
        )

    volume = quad = bav = None
    try:
        volume = float(ConvexHull(vectors).volume)
    except Exception:  # noqa: BLE001 - flat or degenerate shells have no hull
        volume = None
    if cn == 6 and volume:
        l0 = (3 * volume / 4) ** (1 / 3)  # center-to-vertex distance of a regular octahedron
        quad = float(np.mean((lengths / l0) ** 2))
        unit = vectors / lengths[:, None]
        cos = np.clip(unit @ unit.T, -1, 1)
        angles = np.degrees(np.arccos(cos[np.triu_indices(6, 1)]))
        cis = np.sort(angles)[:12]  # the 12 cis angles (the 3 trans angles are near 180)
        bav = float(np.sum((cis - 90) ** 2) / 11)
    return Polyhedron(
        index=index,
        element=structure[index].specie.symbol,
        coordination=cn,
        shape=shape,
        shape_score=None if score is None else round(float(score), 3),
        distortion_index=round(float(np.mean(np.abs(lengths - mean)) / mean), 5),
        quadratic_elongation=None if quad is None else round(quad, 5),
        bond_angle_variance=None if bav is None else round(bav, 3),
        volume=None if volume is None else round(volume, 3),
    )


def linkages(structure: Structure, model: IonicModel) -> Linkages:
    """Connectivity of the framework polyhedra (CN <= 6), counting periodic images apart."""
    cations = [i for i, s in enumerate(structure) if not model.is_anion(s.specie.symbol)]
    shells = {i: anion_shell(structure, i, model) for i in cations}
    framework = {i for i, shell in shells.items() if 3 <= len(shell) <= 6}
    # anion index -> [(cation, cation image seen from the anion in cell 0, vector anion->cation)]
    owners: dict[int, list[tuple[int, tuple[int, ...], np.ndarray]]] = defaultdict(list)
    for i in framework:
        for n in shells[i]:
            image = tuple(-int(v) for v in n.image)
            owners[n.index].append((i, image, structure[i].coords - n.coords))

    shared: dict[tuple, int] = defaultdict(int)
    pair_angles: dict[tuple, list[float]] = defaultdict(list)
    for holders in owners.values():
        for (a, ia, va), (b, ib, vb) in itertools.combinations(holders, 2):
            if (a, ia) == (b, ib):
                continue
            offset = tuple(y - x for x, y in zip(ia, ib, strict=True))
            back = tuple(-o for o in offset)
            key = (a, b, offset) if (a, offset) <= (b, back) else (b, a, back)
            shared[key] += 1
            if len(shells[a]) == 6 and len(shells[b]) == 6:
                cos = va @ vb / (np.linalg.norm(va) * np.linalg.norm(vb))
                pair_angles[key].append(round(float(np.degrees(np.arccos(np.clip(cos, -1, 1)))), 2))
    kinds = [1 if c == 1 else 2 if c == 2 else 3 for c in shared.values()]
    # B-X-B angles through corner-shared anions only (edge sharing forces ~90-100°).
    angles = sorted(a for key, values in pair_angles.items() if shared[key] == 1 for a in values)
    corner_only = kinds.count(2) == 0 and kinds.count(3) == 0
    return Linkages(
        corner=kinds.count(1),
        edge=kinds.count(2),
        face=kinds.count(3),
        bxb_angles=angles,
        # Octahedral tilt in the perovskite sense: only for purely corner-sharing frameworks.
        mean_tilt=round(float(np.mean([(180 - a) / 2 for a in angles])), 2)
        if angles and corner_only
        else None,
    )


def dopant_arrangements(
    structure: Structure, parent: Structure, replaced: dict[str, list[int]]
) -> list[DopantArrangement]:
    out = []
    for element, sites in replaced.items():
        original = parent[sites[0]].specie.symbol
        same = [i for i, s in enumerate(parent) if s.specie.symbol == original]
        spacing = min(
            (parent.get_distance(i, j) for i, j in itertools.combinations(same, 2)),
            default=float(min(parent.lattice.abc)),
        )
        spacing = min(spacing, float(min(parent.lattice.abc)))  # a site's own periodic image
        nearest = [
            round(
                min(
                    [structure.get_distance(i, j) for j in sites if j != i]
                    + [float(min(structure.lattice.abc))]
                ),
                3,
            )
            for i in sites
        ]
        out.append(
            DopantArrangement(
                element=element,
                sites=sites,
                nearest_distances=nearest,
                shortest=min(nearest) if nearest else None,
                cation_spacing=round(spacing, 3),
            )
        )
    return out


ANALYSIS_CELLS = [
    (1, 1, 1),
    (2, 1, 1),
    (1, 2, 1),
    (1, 1, 2),
    (2, 2, 1),
    (2, 1, 2),
    (1, 2, 2),
    (2, 2, 2),
]
MAX_ANALYSIS_SITES = 80


def analysis_cell(structure: Structure, replaced: dict[str, list[int]]) -> tuple[int, int, int]:
    """Smallest repeat of the candidate cell with at least 2 of each dopant (<= 80 atoms)."""
    fitting = [m for m in ANALYSIS_CELLS if len(structure) * math.prod(m) <= MAX_ANALYSIS_SITES]
    for m in fitting:
        if all(len(sites) * math.prod(m) >= 2 for sites in replaced.values()):
            return m
    return fitting[-1]


def rank_orderings(
    structure: Structure, parent: Structure, replaced: dict[str, list[int]], model: IonicModel
) -> OrderingRank | None:
    """Ewald energy of placements of the same dopants in a repeated cell (the candidate's own
    ordering, repeated, is one of them)."""
    m = analysis_cell(structure, replaced)
    big, big_parent = structure * m, parent * m
    big_replaced = {el: [i for i, s in enumerate(big) if s.specie.symbol == el] for el in replaced}
    groups = [
        (big_parent[sites[0]].specie.symbol, el, len(sites)) for el, sites in big_replaced.items()
    ]
    pools = [
        [i for i, s in enumerate(big_parent) if s.specie.symbol == orig] for orig, _, _ in groups
    ]
    total = math.prod(
        math.comb(len(pool), k) for pool, (_, _, k) in zip(pools, groups, strict=True)
    )
    if total < 2:
        return None

    # E = q^T M q with M from unit charges: one Ewald sum for all configurations.
    unit = big_parent.copy()
    unit.add_oxidation_state_by_site([1.0] * len(unit))
    matrix = EwaldSummation(unit).total_energy_matrix
    base = np.array([model.oxidation_states.get(s.specie.symbol, 0.0) for s in big_parent])

    def energy(choice: list[list[int]]) -> float:
        q = base.copy()
        used: set[int] = set()
        for (_, new, _), sites in zip(groups, choice, strict=True):
            if used & set(sites):
                return math.inf  # two substitutions on the same site
            used |= set(sites)
            q[sites] = model.oxidation_states[new]
        return float(q @ matrix @ q) / len(big_parent)

    truncated = total > MAX_ORDERINGS
    if truncated:  # an even, reproducible random sample instead of the first N
        rng = random.Random(0)
        choices = [
            [sorted(rng.sample(pool, k)) for pool, (_, _, k) in zip(pools, groups, strict=True)]
            for _ in range(MAX_ORDERINGS)
        ]
    else:
        choices = [
            list(map(list, c))
            for c in itertools.product(
                *(
                    itertools.combinations(pool, k)
                    for pool, (_, _, k) in zip(pools, groups, strict=True)
                )
            )
        ]
    chosen = energy([big_replaced[new] for _, new, _ in groups])
    energies = [e for e in map(energy, choices) if math.isfinite(e)]
    if not energies:
        return None
    lowest = min(min(energies), chosen)
    rel = sorted(round((e - lowest) * 1000, 2) for e in energies)
    distinct = sorted(set(rel))
    chosen_rel = round((chosen - lowest) * 1000, 2)
    return OrderingRank(
        energies=rel,
        chosen=chosen_rel,
        chosen_rank=1 + sum(1 for d in distinct if d < chosen_rel - 0.01),
        distinct=len(distinct),
        total=total,
        truncated=truncated,
        analysis_cell=m,
        method=(
            "Ewald summation with formal (average) charges in a repeated cell; "
            "a point-charge model for ranking only"
        ),
    )


def analyze(
    structure: Structure,
    focus: list[int] | None = None,
    parent: Structure | None = None,
    replaced: dict[str, list[int]] | None = None,
    rank: bool = True,
) -> SpatialAnalysis:
    """focus: sites to describe in detail (default: one site per cation element).

    parent is the reference for the symmetry change. rank=False skips the dopant arrangement
    and ordering rank (use it for a relaxed geometry: relaxation does not move ions between
    sites, so the arrangement and its rank are those of the unrelaxed candidate).
    """
    model = ionic_model(structure)
    symmetry = symmetry_of(structure)
    notes = [
        (
            "Geometry of the model structure. An ordered supercell is one model of a "
            "disordered solid solution; its symmetry and arrangement are properties of that model."
        ),
        "Small supercells cannot show every tilt pattern (many need a √2 × √2 or larger cell).",
    ]
    if model is None:
        return SpatialAnalysis(
            symmetry=symmetry,
            polyhedra=[],
            linkages=Linkages(corner=0, edge=0, face=0, bxb_angles=[], mean_tilt=None),
            findings=["No anion: polyhedral analysis needs an ionic material."],
            notes=notes,
        )
    if focus is None:
        seen: dict[str, int] = {}
        for i, s in enumerate(structure):
            if not model.is_anion(s.specie.symbol):
                seen.setdefault(s.specie.symbol, i)
        focus = sorted(seen.values())
    polyhedra = [p for p in (polyhedron(structure, i, model) for i in focus) if p]
    links = linkages(structure, model)

    findings: list[str] = []
    parent_symmetry = symmetry_of(parent) if parent is not None else None
    if parent_symmetry and parent_symmetry.number and symmetry.number:
        if symmetry.number != parent_symmetry.number:
            findings.append(
                f"Symmetry {parent_symmetry.spacegroup} → {symmetry.spacegroup}: optical class "
                f"{parent_symmetry.optical_class} → {symmetry.optical_class}. In this ordered model "
                "the material would be birefringent if the class is not isotropic."
            )
        else:
            findings.append(f"Symmetry kept ({symmetry.spacegroup}, {symmetry.optical_class}).")
    for p in polyhedra:
        if p.distortion_index > 0.02:
            findings.append(
                f"{p.element}{p.index} {p.shape} is distorted (Δ = {p.distortion_index:.3f})."
            )
    if links.mean_tilt is not None and links.mean_tilt > 1:
        findings.append(f"Corner-sharing octahedra are tilted (mean {links.mean_tilt:.1f}°).")

    parent_polyhedra: list[Polyhedron] = []
    parent_links = None
    parent_model = ionic_model(parent) if parent is not None else None
    if parent is not None and parent_model is not None:
        parent_polyhedra = [p for p in (polyhedron(parent, i, parent_model) for i in focus) if p]
        parent_links = linkages(parent, parent_model)

    dopants, ordering = [], None
    if parent is not None and replaced and rank:
        dopants = dopant_arrangements(structure, parent, replaced)
        for d in dopants:
            if (
                d.shortest is not None
                and len(d.sites) > 1
                and d.shortest <= d.cation_spacing * 1.05
            ):
                findings.append(
                    f"{d.element} ions sit on neighboring sites ({d.shortest:.2f} Å): clustered."
                )
        ordering = rank_orderings(structure, parent, replaced, model)
        if ordering and ordering.distinct == 1:
            findings.append(
                "Every arrangement has the same Ewald energy (same charges), so the point-charge "
                "model cannot rank them; size effects need relaxation (CHGNet)."
            )
        elif ordering:
            sample = " (random sample)" if ordering.truncated else ""
            findings.append(
                f"This ordering ranks {ordering.chosen_rank} of {ordering.distinct} distinct "
                f"arrangements{sample} by Ewald energy (+{ordering.chosen:.1f} meV/atom above the "
                "lowest)."
            )
    return SpatialAnalysis(
        symmetry=symmetry,
        parent_symmetry=parent_symmetry,
        polyhedra=polyhedra,
        linkages=links,
        parent_polyhedra=parent_polyhedra,
        parent_linkages=parent_links,
        dopants=dopants,
        ordering=ordering,
        findings=findings,
        notes=notes,
    )
