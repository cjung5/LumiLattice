import pytest
from fastapi.testclient import TestClient
from pymatgen.core import Lattice, Structure

from app.main import app
from app.models.candidates import Substitution
from app.models.evidence import Provenance
from app.storage.memory import get_store
from app.tools import ewald
from app.tools.candidates import create_candidate
from app.tools.ewald import Arrangements
from app.tools.ionic import ionic_model
from app.tools.registry import ToolError
from app.tools.substitution import substitute, substitute_lowest_ewald

LA_AL = [
    Substitution(element_from="Sr", element_to="La", fraction=0.5),
    Substitution(element_from="Ti", element_to="Al", fraction=0.5),
]


def energy_of(structure: Structure, replaced: dict[str, list[int]]) -> tuple[float, Arrangements]:
    """Point-charge energy of the dopants in `structure`, and every arrangement on its cell."""
    parent = structure.copy()
    origin = {"La": "Sr", "Al": "Ti"}
    for element, sites in replaced.items():
        for i in sites:
            parent.replace(i, origin[element])
    groups = [(origin[el], el, len(sites)) for el, sites in replaced.items()]
    space = Arrangements(parent, groups, ionic_model(structure).oxidation_states)
    return space.energy([replaced[el] for _, el, _ in groups]), space


def test_lowest_ewald_is_the_exhaustive_minimum(srtio3):
    structure, _, replaced, note = substitute_lowest_ewald(srtio3, LA_AL)
    spread, _, _ = substitute(srtio3, LA_AL)

    assert structure.composition.reduced_formula == spread.composition.reduced_formula
    assert all(len(sites) >= 2 for sites in replaced.values())  # the ordering-rank cell
    chosen, space = energy_of(structure, replaced)
    every = space.energies(list(space.every()))
    assert chosen == pytest.approx(every.min())
    assert note.startswith("lowest Ewald energy: the lowest of all")


def test_lowest_ewald_candidate_ranks_first_in_the_3d_view(srtio3):
    store = get_store()
    spread = create_candidate(store, srtio3, Provenance(source="test"), LA_AL)
    lowest = create_candidate(
        store, srtio3, Provenance(source="test"), LA_AL, arrangement="lowest_ewald"
    )
    client = TestClient(app)

    best = client.get(f"/api/candidates/{lowest.candidate_id}/spatial").json()["ordering"]
    other = client.get(f"/api/candidates/{spread.candidate_id}/spatial").json()["ordering"]

    assert lowest.transformation.arrangement == "lowest_ewald"
    assert best["chosen_rank"] == 1 and best["chosen"] == 0
    assert other["chosen_rank"] >= 1  # the spread arrangement is ranked, not necessarily first


def test_sampled_search_finds_a_low_arrangement(srtio3, monkeypatch):
    monkeypatch.setattr(ewald, "EXACT_LIMIT", 5)  # force the random sample + greedy path
    monkeypatch.setattr(ewald, "SEARCH_SAMPLE", 3)
    structure, _, replaced, note = substitute_lowest_ewald(srtio3, LA_AL)

    chosen, space = energy_of(structure, replaced)
    every = space.energies(list(space.every()))
    assert "not guaranteed" in note
    assert chosen <= sorted(every)[len(every) // 2]  # greedy swaps reach the lower half


def test_full_replacement_has_one_arrangement(srtio3):
    structure, _, _, note = substitute_lowest_ewald(
        srtio3, [Substitution(element_from="Sr", element_to="Ba", fraction=1)]
    )
    spread, _, _ = substitute(
        srtio3, [Substitution(element_from="Sr", element_to="Ba", fraction=1)]
    )
    assert structure == spread and "one arrangement" in note


def test_metal_host_has_no_formal_charges():
    copper = Structure.from_spacegroup("Fm-3m", Lattice.cubic(3.61), ["Cu"], [[0, 0, 0]])
    with pytest.raises(ToolError, match="anion"):
        substitute_lowest_ewald(
            copper, [Substitution(element_from="Cu", element_to="Ni", fraction=0.5)]
        )


def test_api_accepts_the_arrangement_option(srtio3, monkeypatch):
    from app.api import candidates as candidates_api

    monkeypatch.setattr(
        candidates_api,
        "load_host",
        lambda store, mp, **host: (srtio3, Provenance(source="test"), None),
    )
    body = {
        "host": {"material_id": "mp-5229"},
        "substitutions": [s.model_dump() for s in LA_AL],
        "arrangement": "lowest_ewald",
    }
    response = TestClient(app).post("/api/candidates", json=body)

    assert response.status_code == 200
    transformation = response.json()["transformation"]
    assert transformation["arrangement"] == "lowest_ewald"
    assert transformation["site_selection"].startswith("lowest Ewald energy")


def test_periodic_image_chains_are_not_called_clustering(srtio3):
    lowest = create_candidate(
        get_store(), srtio3, Provenance(source="test"), LA_AL, arrangement="lowest_ewald"
    )
    body = TestClient(app).get(f"/api/candidates/{lowest.candidate_id}/spatial").json()

    la = next(d for d in body["dopants"] if d["element"] == "La")
    assert la["periodic_chains"]  # one host cell thick along b and c
    assert any("periodic images" in f for f in body["findings"])
    assert not any("La ions sit on neighboring sites" in f for f in body["findings"])
