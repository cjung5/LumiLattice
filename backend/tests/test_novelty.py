from types import SimpleNamespace

import pytest

from app.models.candidates import Substitution
from app.models.evidence import PropertyValue, Provenance
from app.models.materials import LiteratureResult, MaterialRecord, PaperEvidence
from app.storage.memory import get_store
from app.tools.candidates import create_candidate, solid_solution_ends
from app.tools.novelty import check_novelty, names_candidate, paper_query
from app.tools.registry import ToolError, UpstreamError

LA_AL = [
    Substitution(element_from="Sr", element_to="La", fraction=0.25),
    Substitution(element_from="Ti", element_to="Al", fraction=0.25),
]


def record(material_id="mp-1", formula="X", theoretical=False):
    pv = PropertyValue(name="x", status="Unknown")
    return MaterialRecord(
        material_id=material_id,
        formula=formula,
        crystal_system=None,
        spacegroup=None,
        spacegroup_number=None,
        nsites=5,
        is_stable=False,
        theoretical=theoretical,
        icsd_ids=[],
        band_gap=pv,
        refractive_index=pv,
        energy_above_hull=pv,
        url="https://example.org/m",
        provenance=Provenance(source="test"),
    )


def paper(title):
    return PaperEvidence(
        title=title,
        authors=[],
        year=2020,
        venue=None,
        doi="10.1/x",
        url=None,
        cited_by_count=None,
        open_access=None,
        open_access_url=None,
        provenance=Provenance(source="test"),
    )


class FakeDb:
    def __init__(self, measured=False, computed=False):
        self.m, self.c = measured, computed

    def measured(self, formula):
        return []

    def measured_gaps(self, formula):
        return [3.0] if self.m else []

    def computed(self, formula):
        return [object()] if self.c else []

    def nearest_known(self, formula):
        return [("SrTiO3", 0.1)]


def clients(exact=(), system=(), cod=(), papers=(), fail=()):
    def search(**query):
        if "chemsys" in query:
            if "system" in fail:
                raise UpstreamError("down")
            return list(system)
        if "exact" in fail:
            raise UpstreamError("down")
        return list(exact)

    def cod_search(formula, limit=5):
        if "cod" in fail:
            raise ToolError("down")
        return list(cod)

    status = {"OpenAlex": "rate limited" if "papers" in fail else "ok"}
    return (
        SimpleNamespace(search=search),
        SimpleNamespace(search=cod_search),
        SimpleNamespace(
            search=lambda q, limit=5: LiteratureResult(papers=list(papers), source_status=status)
        ),
    )


@pytest.fixture
def candidate(srtio3):
    return create_candidate(get_store(), srtio3, Provenance(source="test"), LA_AL)


def run(candidate, db=None, **parts):
    mp, cod, literature = clients(**parts)
    return check_novelty(candidate, mp, cod, literature, db or FakeDb())


def test_observed_material_is_known(candidate):
    assert run(candidate, exact=[record()]).level == "known"
    assert run(candidate, db=FakeDb(measured=True)).level == "known"


def test_computed_only_material(candidate):
    assert run(candidate, exact=[record(theoretical=True)]).level == "computed"
    assert run(candidate, db=FakeDb(computed=True)).level == "computed"


def test_related_work_when_there_is_no_exact_match(candidate):
    assert run(candidate, system=[record(formula="LaSr2Ti2AlO9")]).level == "related"
    named = paper("Dielectric properties of SrTiO3-LaAlO3 solid solutions")
    result = run(candidate, papers=[named])
    assert result.level == "related"
    assert (
        next(c for c in result.checks if c.id == "papers").items[0].label.startswith("Dielectric")
    )


def test_unreported_when_nothing_is_found(candidate):
    result = run(candidate, papers=[paper("Superconductivity in copper oxides")])
    assert result.level == "unreported"
    assert result.complete
    assert "does not mean new" in result.caveat


def test_an_unreachable_source_is_reported(candidate):
    result = run(candidate, fail=("cod", "papers"))
    assert not result.complete
    assert {c.id: c.status for c in result.checks}["cod_exact"] == "unavailable"
    assert {c.id: c.status for c in result.checks}["papers"] == "unavailable"


def test_no_materials_project_key(candidate):
    _, cod, literature = clients()
    result = check_novelty(candidate, None, cod, literature, FakeDb())
    assert not result.complete
    assert result.nearest[0].atoms_differ == 0.1


@pytest.mark.parametrize(
    ("title", "named"),
    [
        ("Phase stability of SrTiO3-LaAlO3 ceramics", True),
        ("SrTiO<sub>3</sub>–LaAlO<sub>3</sub> ceramics", True),
        ("La and Al co-doped SrTiO3", True),
        ("Lattice dynamics and alloys of SrTiO3", False),
        ("La-doped SrTiO3", False),  # no Al
        ("LaAlO3 single crystals", False),
    ],
)
def test_which_titles_name_the_system(candidate, title, named):
    ends = solid_solution_ends("SrTiO3", candidate.transformation.lineage)
    assert names_candidate(title, candidate, ends) is named


def test_paper_query_uses_the_end_members(candidate):
    ends = solid_solution_ends("SrTiO3", candidate.transformation.lineage)
    assert paper_query(candidate, ends) == "SrTiO3 LaAlO3 solid solution"
