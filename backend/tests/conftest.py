import pytest
from pymatgen.core import Lattice, Structure


@pytest.fixture
def srtio3() -> Structure:
    """Cubic perovskite SrTiO3 (5 sites), built locally for tests."""
    return Structure.from_spacegroup(
        "Pm-3m",
        Lattice.cubic(3.905),
        ["Sr", "Ti", "O"],
        [[0, 0, 0], [0.5, 0.5, 0.5], [0.5, 0.5, 0]],
    )
