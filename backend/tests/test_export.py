import io

import pytest
from fastapi.testclient import TestClient
from pymatgen.io.cif import CifParser

from app.main import app
from app.models.candidates import Relaxation, Substitution
from app.models.evidence import Provenance
from app.storage.memory import get_store
from app.tools.candidates import create_candidate
from app.tools.export import cif_text


def make_pair(srtio3):
    """A candidate and a child candidate made from it."""
    store = get_store()
    parent = create_candidate(
        store,
        srtio3,
        Provenance(source="CIF upload", reference="COD 1512124"),
        [Substitution(element_from="Ti", element_to="Zr", fraction=0.5)],
    )
    _, parent_structure = store.get(parent.candidate_id)
    child = create_candidate(
        store,
        parent_structure,
        Provenance(source="LumiLattice candidate", reference=parent.candidate_id),
        [Substitution(element_from="Sr", element_to="Ba", fraction=0.5)],
        parent.candidate_id,
    )
    return parent, child


def test_cif_export_has_provenance_header_and_parses(srtio3):
    _, child = make_pair(srtio3)
    response = TestClient(app).get(f"/api/candidates/{child.candidate_id}/export.cif")

    assert response.status_code == 200
    assert f'filename="{child.candidate_id}.cif"' in response.headers["content-disposition"]
    text = response.text
    assert text.isascii()
    assert "# Original host: CIF upload COD 1512124" in text  # the root host, not the parent
    assert "Ti->Zr 50%" in text and "Sr->Ba 50%" in text
    assert "not relaxed" in text
    structure = CifParser.from_str(text).parse_structures(primitive=False)[0]
    assert len(structure) == len(child.structure.sites)
    assert structure.composition.reduced_formula == child.formula


def test_relaxed_cif_needs_a_relaxation(srtio3):
    _, child = make_pair(srtio3)
    response = TestClient(app).get(f"/api/candidates/{child.candidate_id}/export.cif?relaxed=true")
    assert response.status_code == 400


def test_json_record_has_ancestry_score_spatial_and_sources(srtio3):
    parent, child = make_pair(srtio3)
    client = TestClient(app)
    response = client.get(
        f"/api/candidates/{child.candidate_id}/export.json",
        params={"target_n": 2.2, "min_band_gap": 3.0, "forbidden": "Pb, Cd"},
    )

    assert response.status_code == 200
    assert "record.json" in response.headers["content-disposition"]
    record = response.json()
    assert record["format"] == "lumilattice.candidate-record/1"
    assert record["candidate"]["candidate_id"] == child.candidate_id
    assert [a["candidate_id"] for a in record["ancestry"]] == [parent.candidate_id]
    assert record["goal"]["forbidden_elements"] == ["Pb", "Cd"]
    assert {c["id"] for c in record["goal_score"]["criteria"]} >= {"n", "band_gap"}
    assert record["spatial"]["unrelaxed"]["symmetry"]["spacegroup"]
    assert record["spatial"]["relaxed"] is None
    sources = {s["name"]: s for s in record["data_sources"]}
    cod = sources["Crystallography Open Database"]
    assert cod["license"] == "CC0" and cod["url"].endswith("/1512124.html")
    assert "pymatgen" in sources
    assert set(record["evidence_tags"]) == {"Experimental", "DFT-computed", "Heuristic", "Unknown"}
    assert record["caveats"]

    no_goal = client.get(f"/api/candidates/{parent.candidate_id}/export.json").json()
    assert no_goal["goal"] is None and no_goal["goal_score"] is None
    assert no_goal["ancestry"] == []


def test_export_of_unknown_candidate_is_404():
    client = TestClient(app)
    assert client.get("/api/candidates/LL-9999/export.cif").status_code == 404
    assert client.get("/api/candidates/LL-9999/export.json").status_code == 404


def test_cif_header_keeps_symbols_readable_in_ascii(srtio3):
    _, child = make_pair(srtio3)
    relaxation = Relaxation(
        method="CHGNet, fmax 0.1 eV/Å",
        converged=True,
        steps=1,
        energy_per_atom=0.0,
        lattice_change=(0.0, 0.0, 0.0),
        volume_change=0.0,
        max_displacement=0.0,
        structure=child.structure,
        assessment=child.assessment,
    )
    text = cif_text(child.model_copy(update={"relaxation": relaxation}), [], relaxed=True)
    header = text.split("data_")[0]
    assert "fmax 0.1 eV/A" in header and "?" not in header


def test_cif_export_reads_in_ase(srtio3):
    ase_io = pytest.importorskip("ase.io")  # installed with the optional relax group
    _, child = make_pair(srtio3)
    text = TestClient(app).get(f"/api/candidates/{child.candidate_id}/export.cif").text
    atoms = ase_io.read(io.StringIO(text), format="cif")
    assert len(atoms) == len(child.structure.sites)
