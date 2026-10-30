"""Evaluate refractiveindex.info data pages (formula 1-9 and tabulated n, k).

Wavelengths are in µm, as in the database. Formulas follow the database's
"Dispersion formulas" document. Values outside a page's wavelength range are not
extrapolated: the functions return None.
"""

import itertools
import math
from collections.abc import Sequence
from typing import Any


def _sellmeier(lam: float, c: Sequence[float], squared_poles: bool) -> float:
    total = 1 + c[0]
    for i in range(1, len(c) - 1, 2):
        pole = c[i + 1] if squared_poles else c[i + 1] ** 2
        total += c[i] * lam**2 / (lam**2 - pole)
    return math.sqrt(total)


def formula_n(kind: int, coefficients: Sequence[float], lam: float) -> float | None:
    c = list(coefficients) + [0.0] * 17  # missing trailing coefficients are zero
    if kind == 1:  # Sellmeier
        n = _sellmeier(lam, coefficients, squared_poles=False)
    elif kind == 2:  # Sellmeier-2
        n = _sellmeier(lam, coefficients, squared_poles=True)
    elif kind == 3:  # Polynomial
        n2 = c[0] + sum(c[i] * lam ** c[i + 1] for i in range(1, len(coefficients) - 1, 2))
        n = math.sqrt(n2)
    elif kind == 4:  # RefractiveIndex.INFO
        n2 = (
            c[0]
            + c[1] * lam ** c[2] / (lam**2 - c[3] ** c[4])
            + c[5] * lam ** c[6] / (lam**2 - c[7] ** c[8])
            + sum(c[i] * lam ** c[i + 1] for i in range(9, len(coefficients) - 1, 2))
        )
        n = math.sqrt(n2)
    elif kind == 5:  # Cauchy
        n = c[0] + sum(c[i] * lam ** c[i + 1] for i in range(1, len(coefficients) - 1, 2))
    elif kind == 6:  # Gases
        n = 1 + c[0] + sum(c[i] / (c[i + 1] - lam**-2) for i in range(1, len(coefficients) - 1, 2))
    elif kind == 7:  # Herzberger
        f = 1 / (lam**2 - 0.028)
        n = c[0] + c[1] * f + c[2] * f**2 + c[3] * lam**2 + c[4] * lam**4 + c[5] * lam**6
    elif kind == 8:  # Retro
        a = c[0] + c[1] * lam**2 / (lam**2 - c[2]) + c[3] * lam**2
        n = math.sqrt((1 + 2 * a) / (1 - a))
    elif kind == 9:  # Exotic
        n2 = c[0] + c[1] / (lam**2 - c[2]) + c[3] * (lam - c[4]) / ((lam - c[4]) ** 2 + c[5])
        n = math.sqrt(n2)
    else:
        return None
    return n if math.isfinite(n) and n > 0 else None


def _interpolate(points: list[tuple[float, float]], lam: float) -> float | None:
    points = sorted(points)
    if not points or lam < points[0][0] or lam > points[-1][0]:
        return None
    for (x0, y0), (x1, y1) in itertools.pairwise(points):
        if x0 <= lam <= x1:
            return y0 if x1 == x0 else y0 + (y1 - y0) * (lam - x0) / (x1 - x0)
    return points[-1][1] if lam == points[-1][0] else None


def _rows(text: str) -> list[list[float]]:
    rows = []
    for line in text.strip().splitlines():
        try:
            rows.append([float(x) for x in line.split()])
        except ValueError:
            continue
    return rows


def evaluate(data: list[dict[str, Any]], lam: float) -> tuple[float | None, float | None]:
    """Return (n, k) at wavelength lam (µm) from a page's DATA list."""
    n = k = None
    for entry in data:
        kind = str(entry.get("type", ""))
        if kind.startswith("formula"):
            low, high = (float(x) for x in str(entry["wavelength_range"]).split())
            if low <= lam <= high:
                coefficients = [float(x) for x in str(entry["coefficients"]).split()]
                n = formula_n(int(kind.split()[1]), coefficients, lam)
        elif kind == "tabulated nk":
            rows = _rows(entry["data"])
            n = _interpolate([(r[0], r[1]) for r in rows if len(r) >= 2], lam)
            k = _interpolate([(r[0], r[2]) for r in rows if len(r) >= 3], lam)
        elif kind == "tabulated n":
            n = _interpolate([(r[0], r[1]) for r in _rows(entry["data"]) if len(r) >= 2], lam)
        elif kind == "tabulated k":
            k = _interpolate([(r[0], r[1]) for r in _rows(entry["data"]) if len(r) >= 2], lam)
    return n, k


def wavelength_range(data: list[dict[str, Any]]) -> tuple[float, float] | None:
    lows, highs = [], []
    for entry in data:
        kind = str(entry.get("type", ""))
        if kind.startswith("formula"):
            low, high = (float(x) for x in str(entry["wavelength_range"]).split())
        elif kind.startswith("tabulated"):
            xs = [r[0] for r in _rows(entry["data"]) if r]
            if not xs:
                continue
            low, high = min(xs), max(xs)
        else:
            continue
        lows.append(low)
        highs.append(high)
    return (min(lows), max(highs)) if lows else None
