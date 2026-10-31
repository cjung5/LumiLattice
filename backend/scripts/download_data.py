"""Download the raw reference datasets into data/raw/ (not committed; see .gitignore).

Run from backend/:
    uv run python -m scripts.download_data
"""

import hashlib
import sys
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw"

# Pinned versions, so the reference database can be rebuilt exactly.
DATASETS = [
    {
        "path": RAW_DIR / "jarvis" / "jdft_3d-9-24-2025.json.zip",
        "url": "https://ndownloader.figshare.com/files/64391379",
        "sha256": "f9e0a3309f0000d5de1ec9e49c93963109ea45e63f451103f8f6595d2eabf7f5",
        "about": "JARVIS-DFT 3D, 2025-09-24 (CC BY 4.0), doi:10.6084/m9.figshare.6815699",
    },
    {
        "path": RAW_DIR / "refractiveindex" / "rii-database-2026-05-24.zip",
        "url": "https://github.com/polyanskiy/refractiveindex.info-database/releases/download/"
        "v2026-05-24/rii-database-2026-05-24.zip",
        "sha256": "6cdebebd17fe02b6dc2b03189e15e6c689afc6619c558e1df7b9ac307b6d14eb",
        "about": "refractiveindex.info database, release 2026-05-24 (CC0)",
    },
    {
        "path": RAW_DIR / "expt_gap" / "zhuo_gap_expt.csv",
        "url": "https://ndownloader.figshare.com/files/13464431",
        "sha256": "b204d8d792451cd55d2efa1163f266e6be430dedb96ce35e6ceec54af55ea3bd",
        "about": "Experimental band gaps, Zhuo et al. 2018 (MIT), doi:10.6084/m9.figshare.7289687.v1",
    },
    {
        "path": RAW_DIR / "cole" / "dong_cole_bandgap_database_v2.zip",
        "url": "https://ndownloader.figshare.com/files/31781996",
        "sha256": "47c58e1e818b8935b40511672a7bb69af7c360452211ec657d86b97e7e94a639",
        "about": "Text-mined band gaps, Dong & Cole 2022 (MIT), doi:10.6084/m9.figshare.14079863.v1",
    },
    {
        "path": RAW_DIR / "cole" / "zhao_cole_refractive_index.csv",
        "url": "https://ndownloader.figshare.com/files/33982973",
        "sha256": "d8e440eb76379dc921cef0246e01c8f7f102cd4a46a8950cbddb330d8c6d4c49",
        "about": "Text-mined n, Zhao & Cole 2022 (CC BY 4.0), doi:10.6084/m9.figshare.12781142.v2",
    },
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    for item in DATASETS:
        path: Path = item["path"]
        if path.exists() and sha256(path) == item["sha256"]:
            print(f"ok      {path.relative_to(REPO_ROOT)}")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        print(f"get     {item['about']}")
        with httpx.stream("GET", item["url"], follow_redirects=True, timeout=300) as response:
            response.raise_for_status()
            with path.open("wb") as f:
                for chunk in response.iter_bytes():
                    f.write(chunk)
        if sha256(path) != item["sha256"]:
            print(f"FAIL    checksum mismatch for {path.name}")
            return 1
        print(f"ok      {path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
