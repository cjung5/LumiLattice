import pytest
from pymatgen.io.cif import CifWriter

from app.models.evidence import Provenance
from app.tools.registry import ToolError
from app.tools.structures import parse_cif, structure_payload


def test_structure_payload(srtio3):
    payload = structure_payload(srtio3, Provenance(source="test"))

    assert payload.formula == "SrTiO3"
    assert payload.spacegroup == "Pm-3m"
    assert payload.spacegroup_number == 221
    assert payload.lattice.a == pytest.approx(3.905)
    assert [s.index for s in payload.sites] == [0, 1, 2, 3, 4]
    assert "_atom_site_fract_x" in payload.cif


def test_parse_cif_round_trip(srtio3):
    payload = parse_cif(str(CifWriter(srtio3)), "srtio3.cif")

    assert payload.formula == "SrTiO3"
    assert len(payload.sites) == 5
    assert payload.provenance.source == "CIF upload"
    assert payload.provenance.reference == "srtio3.cif"


def test_parse_cif_rejects_garbage():
    with pytest.raises(ToolError):
        parse_cif("this is not a cif", "bad.cif")
