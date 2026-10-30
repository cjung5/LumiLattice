"""Build backend/data/reference.sqlite from the raw JARVIS and refractiveindex.info files.

The full JARVIS JSON needs about 1.7 GB of RAM to load, so the server cannot read it.
This script keeps only the fields the app shows. Run from backend/ after download_data:
    uv run python -m scripts.build_reference_db
"""

import html
import json
import math
import re
import sqlite3
import statistics
import sys
import zipfile
from datetime import UTC, datetime

import yaml
from pymatgen.core import Composition

from app.config import BACKEND_DIR
from app.tools.dispersion import evaluate, wavelength_range
from scripts.download_data import DATASETS, REPO_ROOT, sha256

OUT = BACKEND_DIR / "data" / "reference.sqlite"
JARVIS_ZIP, RII_ZIP = DATASETS[0]["path"], DATASETS[1]["path"]
WAVELENGTHS = {"n_450": 0.45, "n_550": 0.55, "n_650": 0.65}
# n(λ) curve for charts: 380-780 nm every 10 nm (None outside the measured range).
CURVE_NM = list(range(380, 781, 10))

SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE jarvis (
    jid TEXT PRIMARY KEY, formula TEXT NOT NULL, mp_id TEXT, spg_number INTEGER,
    spg_symbol TEXT, has_icsd INTEGER, optb88vdw_gap REAL, mbj_gap REAL, hse_gap REAL,
    eps_optb88vdw REAL, eps_mbj REAL
);
CREATE INDEX jarvis_formula ON jarvis(formula);
CREATE TABLE ri_pages (
    id INTEGER PRIMARY KEY, formula TEXT NOT NULL, book TEXT, page TEXT, title TEXT,
    category TEXT, direction TEXT, reference TEXT, doi TEXT, comments TEXT,
    wl_min REAL, wl_max REAL, n_450 REAL, n_550 REAL, n_650 REAL, k_550 REAL, data_path TEXT,
    curve TEXT
);
CREATE INDEX ri_formula ON ri_pages(formula);
"""


def reduced(formula: str) -> str | None:
    try:
        comp = Composition(formula)
    except (ValueError, KeyError):
        return None
    return comp.reduced_formula if comp.valid and comp.num_atoms > 0 else None


def number(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) and math.isfinite(value) else None


def mean_eps(entry: dict, prefix: str) -> float | None:
    values = [number(entry.get(f"{prefix}{axis}")) for axis in "xyz"]
    values = [v for v in values if v is not None and v >= 1]
    return statistics.fmean(values) if values else None


def build_jarvis(db: sqlite3.Connection) -> int:
    with zipfile.ZipFile(JARVIS_ZIP) as z:
        records = json.loads(z.read(z.namelist()[0]))
    rows = []
    for e in records:
        if e.get("typ") not in (None, "bulk"):
            continue
        formula = reduced(str(e.get("formula", "")))
        gaps = [number(e.get(k)) for k in ("optb88vdw_bandgap", "mbj_bandgap", "hse_gap")]
        eps = [mean_eps(e, "eps"), mean_eps(e, "meps")]
        if formula is None or all(v is None for v in gaps + eps):
            continue
        reference = str(e.get("reference") or "")
        spg = str(e.get("spg_number") or "")
        rows.append(
            (
                e["jid"],
                formula,
                reference if reference.startswith("mp-") else None,
                int(spg) if spg.isdigit() else None,
                e.get("spg_symbol"),
                int(bool(str(e.get("icsd") or "").strip() not in ("", "na"))),
                *gaps,
                *eps,
            )
        )
    db.executemany("INSERT INTO jarvis VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    return len(rows)


def _r(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def plain(text: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", text or ""))).strip()


def build_refractiveindex(db: sqlite3.Connection) -> int:
    rows = []
    with zipfile.ZipFile(RII_ZIP) as z:
        catalog = yaml.load(z.read("database/catalog-nk.yml"), Loader=yaml.CSafeLoader)
        main = next(shelf for shelf in catalog if shelf.get("SHELF") == "main")
        for book in main.get("content", []):
            if "BOOK" not in book:
                continue
            formula = reduced(str(book["BOOK"]))
            if formula is None:
                continue
            category = ""
            for item in book.get("content", []):
                if "DIVIDER" in item:
                    category = plain(item["DIVIDER"])
                    continue
                if "PAGE" not in item:
                    continue
                if re.search(r"model|simulation", category, re.IGNORECASE):
                    continue  # computed pages; the app tags this table as Experimental
                page = yaml.load(z.read(f"database/data/{item['data']}"), Loader=yaml.CSafeLoader)
                data = page.get("DATA") or []
                span = wavelength_range(data)
                values = {name: evaluate(data, lam)[0] for name, lam in WAVELENGTHS.items()}
                if span is None or all(v is None for v in values.values()):
                    continue  # no n in the visible range
                references = page.get("REFERENCES") or ""
                doi = re.search(r"doi\.org/([^\"'<\s]+)", references)
                direction = (page.get("CONDITIONS") or {}).get("direction")
                rows.append(
                    (
                        formula,
                        str(book["BOOK"]),
                        str(item["PAGE"]),
                        plain(item.get("name")),
                        category,
                        str(direction) if direction else None,
                        plain(references)[:600],
                        doi.group(1) if doi else None,
                        plain(page.get("COMMENTS"))[:300] or None,
                        span[0],
                        span[1],
                        values["n_450"],
                        values["n_550"],
                        values["n_650"],
                        evaluate(data, 0.55)[1],
                        f"main/{item['data'].split('main/', 1)[-1]}",
                        json.dumps([_r(evaluate(data, nm / 1000)[0]) for nm in CURVE_NM]),
                    )
                )
    db.executemany(
        "INSERT INTO ri_pages (formula, book, page, title, category, direction, reference, doi, "
        "comments, wl_min, wl_max, n_450, n_550, n_650, k_550, data_path, curve) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    return len(rows)


def main() -> int:
    for item in DATASETS:
        if not item["path"].exists():
            print(f"Missing {item['path']}. Run: uv run python -m scripts.download_data")
            return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    db.executescript(SCHEMA)
    n_jarvis = build_jarvis(db)
    n_pages = build_refractiveindex(db)
    meta = {
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "jarvis": DATASETS[0]["about"],
        "jarvis_sha256": sha256(JARVIS_ZIP),
        "refractiveindex": DATASETS[1]["about"],
        "refractiveindex_sha256": sha256(RII_ZIP),
    }
    db.executemany("INSERT INTO meta VALUES (?, ?)", meta.items())
    db.commit()
    db.execute("VACUUM")
    db.close()
    tmp.replace(OUT)
    size = OUT.stat().st_size / 1e6
    print(
        f"{OUT.relative_to(REPO_ROOT)}: {n_jarvis} JARVIS rows, {n_pages} refractiveindex pages, {size:.1f} MB"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
