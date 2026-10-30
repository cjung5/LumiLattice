import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.evidence import PropertyValue
from app.tools.goals import Goal, threshold_verdict


def pv(**kw) -> PropertyValue:
    return PropertyValue(name="x", status=kw.pop("status", "Heuristic"), **kw)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (pv(value=2.4, status="Experimental"), "meets"),
        (pv(value=2.0, status="Experimental"), "fails"),
        (pv(value_range=(2.3, 2.5)), "meets"),
        (pv(value_range=(2.0, 2.4)), "uncertain"),  # a range that spans the target never "meets"
        (pv(value_range=(1.8, 2.1)), "fails"),
        (pv(status="Unknown"), "unknown"),
        (None, "unknown"),
    ],
)
def test_threshold_verdict(value, expected):
    assert threshold_verdict(value, 2.2) == expected


def test_score_known_formula_cites_evidence():
    response = TestClient(app).post(
        "/api/score",
        json={
            "formula": "SrTiO3",
            "goal": {"target_n": 2.2, "min_band_gap": 3.0, "forbidden_elements": ["Pb"]},
        },
    )
    assert response.status_code == 200
    body = response.json()
    by_id = {c["id"]: c for c in body["criteria"]}
    assert by_id["elements"]["verdict"] == "meets"
    if by_id["n"]["evidence"]["status"] == "Experimental":  # bundled reference DB present
        assert by_id["n"]["verdict"] == "meets"  # SrTiO3 n(550) ≈ 2.43
        assert "Experimental" in by_id["n"]["detail"]


def test_forbidden_element_fails():
    response = TestClient(app).post(
        "/api/score", json={"formula": "PbTiO3", "goal": {"forbidden_elements": ["pb"]}}
    )
    by_id = {c["id"]: c for c in response.json()["criteria"]}
    assert by_id["elements"]["verdict"] == "fails"


def test_goal_defaults():
    goal = Goal()
    assert (goal.target_n, goal.min_band_gap) == (2.2, 3.0)


def test_landscape_and_dispersion_endpoints():
    api = TestClient(app)
    landscape = api.get("/api/landscape").json()
    assert {"measured", "computed", "moss", "notes"} <= landscape.keys()
    [disp] = api.get("/api/dispersion", params={"formulas": "SrTiO3"}).json()
    assert len(disp["wavelengths_nm"]) == len(range(380, 781, 10))
