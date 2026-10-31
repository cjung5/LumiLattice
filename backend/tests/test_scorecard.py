import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.candidates import Substitution
from app.models.evidence import PropertyValue, Provenance
from app.models.optical import EndMemberIndex, OpticalEstimate
from app.storage.memory import get_store
from app.tools.candidates import create_candidate
from app.tools.goals import Goal
from app.tools.reference_db import get_reference_db
from app.tools.scorecard import (
    WEIGHTS,
    build_scorecard,
    gap_points,
    moss_points,
    moss_ratio,
    n_points,
    optical_score,
    ramp,
)
from app.tools.spatial import before_substitution

GOAL = Goal()
LA_AL = [
    Substitution(element_from="Sr", element_to="La", fraction=0.25),
    Substitution(element_from="Ti", element_to="Al", fraction=0.25),
]


def card(candidate, structure, goal=GOAL):
    parent = before_substitution(structure, candidate.transformation)
    return build_scorecard(candidate, structure, parent, goal, get_reference_db())


@pytest.fixture
def stored(srtio3):
    candidate = create_candidate(get_store(), srtio3, Provenance(source="test"), LA_AL)
    return get_store().get(candidate.candidate_id)


def test_weights_sum_to_100():
    assert sum(WEIGHTS.values()) == 100


def test_ramp_is_flat_outside_and_linear_inside():
    anchors = [(1, 0), (2, 50), (4, 100)]
    assert [ramp(x, anchors) for x in (0, 1.5, 3, 9)] == [0, 25, 75, 100]


def test_meeting_the_goal_is_worth_70_points():
    assert n_points(GOAL.target_n, GOAL) == pytest.approx(70)
    assert gap_points(GOAL.min_band_gap, GOAL) == pytest.approx(70)
    assert n_points(1.0, GOAL) == 0 and n_points(9, GOAL) == 100


def test_the_goal_changes_the_points():
    strict = Goal(target_n=2.6, min_band_gap=4)
    assert n_points(2.4, strict) < n_points(2.4, GOAL)
    assert gap_points(3.5, strict) < gap_points(3.5, GOAL)


def test_a_goal_below_the_floor_still_has_rising_points():
    easy = Goal(target_n=1.2, min_band_gap=1.0)
    assert n_points(1.2, easy) == pytest.approx(70)
    assert gap_points(1.0, easy) == pytest.approx(70)


def test_moss_ratio_is_one_on_the_trend():
    n = 95**0.25  # gap of 1 eV on n^4 * Eg = 95 eV
    assert moss_ratio(n, 1) == pytest.approx(1)
    assert moss_points(1) == 50


def test_a_wider_range_gives_a_wider_score(stored):
    candidate, structure = stored
    result = card(candidate, structure)

    n = next(m for m in result.metrics if m.id == "n")
    assert result.low < result.high
    assert n.evidence == "Heuristic" and n.low < n.high
    assert result.low == pytest.approx(sum(m.weight * m.low for m in result.metrics) / 100, abs=0.1)
    assert result.high == pytest.approx(
        sum(m.weight * m.high for m in result.metrics) / 100, abs=0.1
    )


def test_unknown_evidence_counts_as_0_to_100(stored):
    candidate, structure = stored
    unknown = PropertyValue(name="refractive_index", status="Unknown")
    blank = candidate.model_copy(
        update={
            "optical_estimate": OpticalEstimate(estimate=unknown, end_members=[], band_gap=None)
        }
    )
    metrics = {m.id: m for m in card(blank, structure).metrics}

    for metric in ("n", "band_gap", "trade_off"):
        assert (metrics[metric].low, metrics[metric].high) == (0, 100)
        assert metrics[metric].evidence == "Unknown"


def test_trade_off_uses_real_end_member_pairs(stored):
    candidate, structure = stored
    pv = lambda v: PropertyValue(name="x", value=v, status="Experimental")
    ends = [
        EndMemberIndex(formula="A", n=pv(2.4), band_gap=pv(3.0)),
        EndMemberIndex(formula="B", n=pv(2.0), band_gap=pv(5.0)),
    ]
    span = PropertyValue(name="x", value_range=(2.0, 2.4), status="Heuristic")
    gaps = PropertyValue(name="x", value_range=(3.0, 5.0), status="Heuristic")
    paired = candidate.model_copy(
        update={"optical_estimate": OpticalEstimate(estimate=span, band_gap=gaps, end_members=ends)}
    )
    metric = next(m for m in card(paired, structure).metrics if m.id == "trade_off")

    # Not 2.0 with 3.0 eV and 2.4 with 5.0 eV: no end member has those pairs.
    low, high = round(moss_ratio(2.0, 5.0), 2), round(moss_ratio(2.4, 3.0), 2)
    assert metric.value == f"{low:.3g}–{high:.3g}"


def test_a_failed_check_caps_the_fit_metric(stored):
    candidate, structure = stored
    checks = [c.model_copy(update={"status": "pass"}) for c in candidate.assessment.checks]
    checks[0] = checks[0].model_copy(update={"status": "fail"})
    assessment = candidate.assessment.model_copy(update={"checks": checks})
    failed = candidate.model_copy(update={"assessment": assessment})

    assert next(m for m in card(failed, structure).metrics if m.id == "fit").high <= 30


def test_forbidden_elements_are_flagged(stored):
    candidate, structure = stored
    result = card(candidate, structure, Goal(forbidden_elements=["La", "Pb"]))
    assert result.disqualified == ["La"]


def test_isotropy_spans_the_model_and_the_host(stored):
    candidate, structure = stored
    metric = next(m for m in card(candidate, structure).metrics if m.id == "isotropy")
    assert metric.high == 100  # the cubic host
    assert metric.low < 100  # the ordered model has lower symmetry


def test_benchmark_counts_known_materials():
    db = get_reference_db()
    if not db.available:
        pytest.skip("reference.sqlite is not built")
    leaders = sorted(
        (optical_score(p.n, p.band_gap, GOAL) for p in db.landscape().measured), reverse=True
    )
    assert leaders[0] > leaders[-1]


def test_benchmark_in_the_scorecard(stored):
    candidate, structure = stored
    if not get_reference_db().available:
        pytest.skip("reference.sqlite is not built")
    bench = card(candidate, structure).benchmark

    assert bench.size > 100
    assert 0 <= bench.beats_low <= bench.beats_high <= bench.size
    assert bench.host.formula == "SrTiO3"
    assert {e.formula for e in bench.landmarks} >= {"TiO2", "SrTiO3"}
    scores = [e.score for e in bench.landmarks]
    assert scores == sorted(scores, reverse=True)


def test_scorecard_api(stored):
    candidate, _ = stored
    client = TestClient(app)
    body = client.post(
        f"/api/candidates/{candidate.candidate_id}/scorecard", json=GOAL.model_dump()
    )

    assert body.status_code == 200
    assert {m["id"] for m in body.json()["metrics"]} == set(WEIGHTS)
    assert "not a probability" in body.json()["method"]
    assert client.post("/api/candidates/LL-9999/scorecard", json={}).status_code == 404


def test_supply_comes_from_the_composition(stored):
    candidate, structure = stored
    metric = next(m for m in card(candidate, structure).metrics if m.id == "supply")
    assert metric.evidence == "Model"
