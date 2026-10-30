import warnings

from pymatgen.core import Structure
from pymatgen.io.cif import CifParser, CifWriter
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

from app.models.evidence import Provenance
from app.models.materials import Lattice, Site, StructurePayload
from app.tools.registry import ToolError

MAX_SITES = 500


def structure_payload(structure: Structure, provenance: Provenance) -> StructurePayload:
    if len(structure) > MAX_SITES:
        raise ToolError(f"Structure has {len(structure)} sites; the limit is {MAX_SITES}.")
    try:
        spg = SpacegroupAnalyzer(structure, symprec=0.1)
        spacegroup, number = spg.get_space_group_symbol(), spg.get_space_group_number()
    except ValueError:  # incl. SymmetryUndeterminedError; symmetry is optional here
        spacegroup, number = None, None

    lat = structure.lattice
    return StructurePayload(
        formula=structure.composition.reduced_formula,
        spacegroup=spacegroup,
        spacegroup_number=number,
        lattice=Lattice(
            a=round(lat.a, 4),
            b=round(lat.b, 4),
            c=round(lat.c, 4),
            alpha=round(lat.alpha, 3),
            beta=round(lat.beta, 3),
            gamma=round(lat.gamma, 3),
            volume=round(lat.volume, 3),
        ),
        sites=[
            Site(
                index=i,
                species=site.species_string,
                frac_coords=tuple(round(float(x), 5) for x in site.frac_coords),
            )
            for i, site in enumerate(structure)
        ],
        cif=str(CifWriter(structure)),
        provenance=provenance,
    )


def _read_cif(text: str, filename: str) -> tuple[list[Structure], list[str]]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            structures = CifParser.from_str(text).parse_structures(primitive=False)
        except Exception as exc:  # pymatgen raises many error types for bad CIFs
            raise ToolError(f"Cannot read CIF {filename!r}: {exc}") from exc
    if not structures:
        raise ToolError(f"CIF {filename!r} has no structure.")
    # Experimental CIFs (e.g. COD) often label atoms with charges ("Sr2+"). The app works
    # with element symbols and assigns oxidation states itself, so the labels are removed.
    for structure in structures:
        structure.remove_oxidation_states()
    return structures, sorted({str(w.message) for w in caught})[:5]


def parse_cif_structure(text: str, filename: str) -> Structure:
    return _read_cif(text, filename)[0][0]


def parse_cif(text: str, filename: str) -> StructurePayload:
    structures, cif_warnings = _read_cif(text, filename)
    payload = structure_payload(structures[0], Provenance(source="CIF upload", reference=filename))
    payload.warnings = cif_warnings
    if len(structures) > 1:
        payload.warnings.append(f"CIF has {len(structures)} structures; showing the first.")
    return payload
