import json

import pytest
from pymatgen.core import Composition

from app.tools import scorecard
from app.tools.reference_db import (
    GAP_MARGIN_EV,
    MIX_TYPICAL_GAP_ERROR_EV,
    MIX_TYPICAL_N_ERROR,
    N_MARGIN,
)
from scripts.validate_score import (
    area_under_curve,
    end_members,
    margin_holdout,
    range_summary,
    rank_correlation,
    site_groups,
)


def test_site_groups_pair_fractional_elements():
    assert site_groups(Composition("Ga1 As0.4 P0.6")) == [("As", "P")]
    two = site_groups(Composition("Zn0.7 Ga0.3 As0.3 Se0.7"))
    assert len(two) == 2 and {e for group in two for e in group} == {"Zn", "Ga", "As", "Se"}
    assert site_groups(Composition("SrTiO3")) is None


def test_end_members_and_shares():
    comp = Composition("Ga1 As0.4 P0.6")
    ends = dict(end_members(comp, site_groups(comp)))
    assert ends == pytest.approx({"GaAs": 0.4, "GaP": 0.6})


def test_range_summary_counts_cases_inside():
    cases = [
        {"measured": 2.0, "low": 1.0, "high": 3.0, "linear": 2.0},
        {"measured": 0.9, "low": 1.0, "high": 3.0, "linear": 2.0},
        {"measured": 3.4, "low": 1.0, "high": 3.0, "linear": 2.0},
    ]
    summary = range_summary(cases)
    assert summary["inside"]["0"] == pytest.approx(0.333)
    assert summary["inside"]["0.1"] == pytest.approx(0.667)
    assert summary["inside"]["0.5"] == 1
    assert (summary["below_range"], summary["above_range"]) == (1, 1)


def test_margin_is_chosen_on_one_half_and_tested_on_the_other():
    cases = [{"measured": 1.15, "low": 0.0, "high": 1.0} for _ in range(10)]
    result = margin_holdout(cases)
    assert result["chosen_margin_ev"] == 0.2
    assert result["inside_on_test"] == 1
    assert result["tune_cases"] + result["test_cases"] == 10


def test_statistics():
    assert rank_correlation([1, 2, 3], [10, 20, 30]) == 1
    assert rank_correlation([1, 2, 3], [30, 20, 10]) == -1
    assert rank_correlation([1, 1, 1], [1, 2, 3]) is None
    assert area_under_curve([2, 3], [1]) == 1
    assert area_under_curve([1], [1]) == 0.5
    assert area_under_curve([], [1]) is None


def test_validation_report_is_optional(tmp_path, monkeypatch):
    monkeypatch.setattr(scorecard, "VALIDATION_FILE", tmp_path / "missing.json")
    scorecard.load_validation.cache_clear()
    assert scorecard.load_validation() is None
    (tmp_path / "bad.json").write_text(json.dumps({"measured_gap_ranges": {"all": {}}}))
    monkeypatch.setattr(scorecard, "VALIDATION_FILE", tmp_path / "bad.json")
    scorecard.load_validation.cache_clear()
    assert scorecard.load_validation() is None
    scorecard.load_validation.cache_clear()


def test_committed_report_loads_with_the_applied_margins():
    report = json.loads(scorecard.VALIDATION_FILE.read_text())
    scorecard.load_validation.cache_clear()
    loaded = scorecard.load_validation()

    assert loaded is not None
    other = report["oxides"]["gap_reviewed_clear_without_mgzno"]
    assert loaded.oxide_other_rank == other["rank_correlation_midpoint"]
    assert loaded.oxide_other_cases == other["cases"]
    assert report["applied_margins"] == {"gap_ev": GAP_MARGIN_EV, "n": N_MARGIN}


def test_stated_mix_errors_match_the_report():
    oxides = json.loads(scorecard.VALIDATION_FILE.read_text())["oxides"]
    gap = oxides["gap_reviewed_clear"]["median_error_of_linear_mix"]
    n = oxides["n_mined_unreviewed"]["median_error_of_linear_mix"]

    assert round(gap, 1) == MIX_TYPICAL_GAP_ERROR_EV
    assert round(n, 1) == MIX_TYPICAL_N_ERROR
