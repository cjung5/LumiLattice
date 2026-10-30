import pytest

from app.tools.dispersion import evaluate, formula_n, wavelength_range


def test_fused_silica_malitson_sellmeier():
    # Malitson (1965) fused silica, a standard check: n(0.5876 µm) = 1.4585.
    c = [0, 0.6961663, 0.0684043, 0.4079426, 0.1162414, 0.8974794, 9.896161]
    assert formula_n(1, c, 0.5876) == pytest.approx(1.4585, abs=2e-4)


def test_srtio3_bond_page_at_550_nm():
    # Coefficients as published on refractiveindex.info (main/SrTiO3/nk/Bond.yml).
    data = [
        {
            "type": "formula 1",
            "wavelength_range": "0.43 3.8",
            "coefficients": "0 3.042143 0.1475902 1.170065 0.2953086 30.83326 33.18606",
        }
    ]
    n, k = evaluate(data, 0.55)
    assert n == pytest.approx(2.432, abs=2e-3)
    assert k is None
    assert wavelength_range(data) == (0.43, 3.8)


def test_rutile_devore_formula_4():
    data = [
        {
            "type": "formula 4",
            "wavelength_range": "0.43 1.53",
            "coefficients": "5.913 0.2441 0 0.0803 1 0 0 0 1",
        }
    ]
    n, _ = evaluate(data, 0.55)
    assert n == pytest.approx(2.648, abs=2e-3)


def test_no_extrapolation_outside_range():
    data = [{"type": "formula 1", "wavelength_range": "0.6 2.0", "coefficients": "0 1 0.1"}]
    assert evaluate(data, 0.55) == (None, None)


def test_tabulated_nk_interpolation():
    data = [{"type": "tabulated nk", "data": "0.50 2.0 0.10\n0.60 1.8 0.00\n"}]
    n, k = evaluate(data, 0.55)
    assert n == pytest.approx(1.9)
    assert k == pytest.approx(0.05)


def test_cauchy():
    # n = 1.5 + 0.004 / lambda^2
    assert formula_n(5, [1.5, 0.004, -2], 0.5) == pytest.approx(1.516)
