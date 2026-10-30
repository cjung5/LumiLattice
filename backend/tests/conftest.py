import pytest
from pymatgen.core import Lattice, Structure

from app.tools import usage


@pytest.fixture(autouse=True)
def fresh_api_usage():
    """Shared caches and daily caps must not leak between tests."""
    for item in (
        usage.MP_CACHE,
        usage.OPENALEX_CACHE,
        usage.CROSSREF_CACHE,
        usage.ARXIV_CACHE,
        usage.COD_CACHE,
        usage.S2_CACHE,
    ):
        item.clear()
    for cap in (
        usage.MP_CAP,
        usage.OPENALEX_CAP,
        usage.CROSSREF_CAP,
        usage.ARXIV_CAP,
        usage.COD_CAP,
        usage.S2_CAP,
        usage.AGENT_CAP,
    ):
        cap.reset()
    usage.AGENT_RATE.reset()


@pytest.fixture
def srtio3() -> Structure:
    """Cubic perovskite SrTiO3 (5 sites), built locally for tests."""
    return Structure.from_spacegroup(
        "Pm-3m",
        Lattice.cubic(3.905),
        ["Sr", "Ti", "O"],
        [[0, 0, 0], [0.5, 0.5, 0.5], [0.5, 0.5, 0]],
    )
