import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.tools.reference_db import ReferenceDB, get_reference_db, mix_shares, normalize
from app.tools.registry import ToolError
from scripts.build_reference_db import SCHEMA, measured_gap_rows, mined_gap_rows


@pytest.fixture
def tiny_db(tmp_path) -> ReferenceDB:
    """A small database with the real schema; values are test fixtures."""
    path = tmp_path / "ref.sqlite"
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    db.executemany(
        "INSERT INTO ri_pages (formula, book, page, title, category, direction, reference, doi, "
        "comments, wl_min, wl_max, n_450, n_550, n_650, k_550, data_path, curve) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                "AB",
                "AB",
                "x-o",
                "X o",
                "Crystal",
                "o",
                "Ref X",
                "10.1/x",
                None,
                0.4,
                1.0,
                2.1,
                2.0,
                1.9,
                None,
                "p",
                None,
            ),
            (
                "AB",
                "AB",
                "x-e",
                "X e",
                "Crystal",
                "e",
                "Ref X",
                "10.1/x",
                None,
                0.4,
                1.0,
                2.3,
                2.2,
                2.1,
                None,
                "p",
                None,
            ),
            (
                "AB",
                "AB",
                "film",
                "Film",
                "Thin film",
                None,
                "Ref F",
                None,
                None,
                0.4,
                1.0,
                1.8,
                1.7,
                1.6,
                None,
                "p",
                None,
            ),
        ],
    )
    db.executemany(
        "INSERT INTO jarvis VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("JVASP-1", "AB", "mp-1", 1, "P1", 1, 2.0, 3.0, None, 6.25, 4.0),  # n_mbj = 2.0
            ("JVASP-2", "CD", None, 1, "P1", 0, 1.0, None, None, 9.0, None),  # OptB88 only
        ],
    )
    db.executemany("INSERT INTO expt_gaps VALUES (?, ?)", [("AB", 4.0), ("AB", 3.4), ("AB", 3.2)])
    db.execute("INSERT INTO mined_gaps VALUES ('EG', 5.0, 4.6, 5.4, 7)")
    db.execute("INSERT INTO mined_gaps VALUES ('AB', 9.0, 9.0, 9.0, 9)")
    db.commit()
    db.close()
    return ReferenceDB(path)


@pytest.fixture
def real_like_db(tmp_path) -> ReferenceDB:
    """Real formulas with fixture values, so compositions can be parsed."""
    path = tmp_path / "real.sqlite"
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    db.executemany(
        "INSERT INTO jarvis VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("J1", "SrTiO3", None, 1, "P1", 1, 1.0, 1.5, None, 4.0, 5.76),  # n_mbj = 2.4
            ("J2", "LaAlO3", None, 1, "P1", 1, 2.0, 2.5, None, 4.0, 4.0),  # n_mbj = 2.0
        ],
    )
    db.executemany("INSERT INTO expt_gaps VALUES (?, ?)", [("SrTiO3", 3.2), ("LaAlO3", 5.6)])
    db.commit()
    db.close()
    return ReferenceDB(path)


def test_best_n_prefers_measured_bulk(tiny_db):
    best = tiny_db.best_n("AB")

    assert best.status == "Experimental"
    assert best.value == pytest.approx(2.1)  # median of 2.0 (o) and 2.2 (e); thin film ignored
    assert "median of 2 sources" in best.conditions


def test_best_n_falls_back_to_dft(tiny_db):
    best = tiny_db.best_n("CD")

    assert best.status == "DFT-computed"
    assert best.value == pytest.approx(3.0)  # sqrt(9.0), OptB88vdW
    assert best.provenance.method == "OptB88vdW"
    assert "not n(550 nm)" in best.conditions


def test_unknown_formula(tiny_db):
    assert tiny_db.best_n("EF").status == "Unknown"


def test_estimate_range_is_heuristic(tiny_db):
    estimate = tiny_db.estimate(["AB", "CD"])

    assert estimate.estimate.status == "Heuristic"
    assert estimate.estimate.value_range == (1.9, 3.2)  # 2.1-3.0 and the tested 0.2 margin
    assert estimate.estimate.value is None  # a range only, never a single number
    assert [m.n.status for m in estimate.end_members] == ["Experimental", "DFT-computed"]


def test_exact_formula_data_replaces_the_range(tiny_db):
    estimate = tiny_db.estimate(["AB", "CD"], exact="AB")

    assert estimate.estimate.status == "Experimental" and estimate.estimate.value is not None
    assert estimate.band_gap.value == 3.4
    assert tiny_db.estimate(["AB", "CD"], exact="EF").estimate.status == "Heuristic"


def test_a_low_quality_exact_value_does_not_replace_the_range(tiny_db):
    estimate = tiny_db.estimate(["AB", "CD"], exact="CD")  # CD has OptB88vdW values only

    assert estimate.band_gap.status == "Heuristic"
    assert estimate.estimate.status == "Heuristic"


def test_mix_shares_of_a_co_substitution():
    assert mix_shares("Sr3LaTi3AlO12", ["SrTiO3", "LaAlO3"]) == pytest.approx(
        {"SrTiO3": 0.75, "LaAlO3": 0.25}, abs=1e-3
    )


def test_mix_shares_of_two_new_elements_on_one_site():
    assert mix_shares("Sr4Ti2ZrHfO12", ["SrTiO3", "SrZrO3", "SrHfO3"]) == pytest.approx(
        {"SrTiO3": 0.5, "SrZrO3": 0.25, "SrHfO3": 0.25}, abs=1e-3
    )


def test_a_composition_off_the_line_has_no_shares():
    # Sr->La 1/4 with Ti->Al 1/2 cannot be made from SrTiO3 and LaAlO3 alone.
    assert mix_shares("Sr3LaTi2Al2O12", ["SrTiO3", "LaAlO3"]) is None
    assert mix_shares("SrTiO3", ["SrTiO3", "LaAlO3"]) is None  # a pure end member is not a mix


def test_linear_mix_weights_the_end_member_values(real_like_db):
    estimate = real_like_db.estimate(["SrTiO3", "LaAlO3"], exact="Sr3LaTi3AlO12")

    mix = estimate.linear_mix
    assert mix.n == pytest.approx(0.75 * 2.4 + 0.25 * 2.0, abs=1e-3)
    assert mix.band_gap == pytest.approx(0.75 * 3.2 + 0.25 * 5.6, abs=1e-3)
    assert estimate.estimate.value_range == (1.8, 2.6)  # the verdict still uses the range
    assert mix.note and mix.typical_gap_error_ev > 0


def test_no_linear_mix_without_a_candidate_formula(real_like_db):
    assert real_like_db.estimate(["SrTiO3", "LaAlO3"]).linear_mix is None


def test_estimate_needs_two_values(tiny_db):
    assert tiny_db.estimate(["AB", "EF"]).estimate.status == "Unknown"


def test_best_gap_prefers_measured(tiny_db):
    gap = tiny_db.best_gap("AB")

    assert gap.status == "Experimental"
    assert gap.value == 3.4  # the median, not the 3.0 eV TBmBJ value
    assert "Median of 3 reports (3.2–4.0 eV)" in gap.conditions
    assert tiny_db.measured_gaps("AB") == [3.2, 3.4, 4.0]


def test_text_mined_gap_comes_after_compiled_and_before_dft(tiny_db):
    assert tiny_db.best_gap("AB").value == 3.4  # the compiled value, not the 9.0 eV mined one
    mined = tiny_db.best_gap("EG")
    assert mined.value == 5.0 and mined.status == "Experimental"
    assert "text-mined" in mined.conditions and "4.6–5.4 eV" in mined.conditions
    assert mined.provenance.source == "Dong & Cole 2022"


def test_a_wide_spread_of_text_mined_reports_is_not_used(tiny_db):
    tiny_db._db.close()
    db = sqlite3.connect(tiny_db.path)
    db.execute("INSERT INTO mined_gaps VALUES ('CD', 5.7, 3.2, 9.0, 258)")  # like SiO2
    db.commit()
    db.close()
    gap = ReferenceDB(tiny_db.path).best_gap("CD")

    assert gap.status == "DFT-computed" and gap.provenance.source == "JARVIS-DFT"


def test_mined_rows_skip_calculations_rare_formulas_and_fractions():
    header = "Composition,Value,Text\n"
    measured = "\"{'Sr': 1, 'Ti': 1, 'O': 3}\",[3.2],We measured it.\n"
    computed = "\"{'Sr': 1, 'Ti': 1, 'O': 3}\",[1.8],DFT calculations give this.\n"
    rare = "\"{'Ba': 1, 'Ti': 1, 'O': 3}\",[3.1],We measured it.\n"
    fraction = "\"{'Sr': 0.5, 'Ba': 0.5, 'Ti': 1, 'O': 3}\",[3.2],We measured it.\n"
    lines = [header, *[measured] * 5, computed, rare, *[fraction] * 5]
    rows = mined_gap_rows(lines)

    assert [r[0] for r in rows] == ["SrTiO3"]
    assert rows[0][1] == 3.2 and rows[0][4] == 5


def test_best_gap_falls_back_to_dft(tiny_db):
    gap = tiny_db.best_gap("CD")

    assert gap.status == "DFT-computed"
    assert gap.provenance.method == "OptB88vdW"


def test_estimate_range_can_mix_measured_and_dft_gaps(tiny_db):
    gap = tiny_db.estimate(["AB", "CD"]).band_gap

    assert gap.status == "Heuristic"
    assert gap.value_range == (0.7, 3.7)  # 1.0-3.4 and the tested 0.3 eV margin
    assert "mix measured and DFT" in gap.conditions


def test_landscape_marks_which_gaps_are_measured(tiny_db):
    points = {p.formula: p for p in tiny_db.landscape().measured}

    assert points["AB"].band_gap == 3.4 and points["AB"].gap_measured


def test_measured_gap_rows_skip_metal_labels_and_bad_formulas():
    lines = ["composition,Eg (eV)\n", "SrTiO3,3.25\n", "UAl4,0\n", '"AgCNO,65",0\n', "Xx2,1.0\n"]

    assert measured_gap_rows(lines) == [("SrTiO3", 3.25)]


def test_missing_database_is_safe(tmp_path):
    db = ReferenceDB(tmp_path / "missing.sqlite")

    assert db.available is False
    assert db.best_n("SrTiO3").status == "Unknown"


def test_normalize():
    assert normalize("Ti2O4") == "TiO2"
    with pytest.raises(ToolError):
        normalize("Xx2")


def test_bundled_database_srtio3():
    db = get_reference_db()
    if not db.available:
        pytest.skip("reference.sqlite is not built")
    ref = db.reference("SrTiO3")

    assert ref.best_n.status == "Experimental"
    assert ref.best_n.value == pytest.approx(2.432, abs=0.01)  # Bond (1965), 550 nm
    assert any(m.doi == "10.1063/1.1703106" for m in ref.measured)
    assert any(c.mp_id == "mp-5229" for c in ref.computed)
    assert ref.best_gap.status == "Experimental"
    assert 3.0 <= ref.best_gap.value <= 3.5  # reports span 3.0-4.1 eV


def test_parallel_requests_do_not_share_a_connection(tiny_db):
    # API requests run in a thread pool; a shared SQLite connection fails with InterfaceError.
    def lookups(_):
        for _ in range(200):
            tiny_db.best_gap("CD")
            tiny_db.measured("CD")

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(lookups, range(16)))
