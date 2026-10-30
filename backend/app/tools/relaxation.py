"""Optional CHGNet relaxation (spec D5): local installs only.

CHGNet needs PyTorch, which does not fit the 512 MB free server. Install it with
`uv sync --group relax`. CHGNet energies come from a machine-learned potential, so they
are never compared with DFT energies.
"""

import importlib.util
import warnings
from dataclasses import dataclass
from functools import lru_cache
from importlib.metadata import version
from typing import Any

import numpy as np
from pymatgen.core import Structure

from app.tools.registry import ToolError

FMAX = 0.1  # eV/Å
MAX_STEPS = 300
MAX_SITES = 80


def relaxation_available() -> bool:
    return importlib.util.find_spec("chgnet") is not None


@dataclass(frozen=True)
class RelaxOutcome:
    structure: Structure
    steps: int
    converged: bool
    energy_per_atom: float
    method: str


@lru_cache
def _optimizer() -> Any:
    from chgnet.model import StructOptimizer  # imported lazily: optional dependency

    return StructOptimizer()


def relax(structure: Structure) -> RelaxOutcome:
    if not relaxation_available():
        raise ToolError(
            "CHGNet relaxation is available only in a local install "
            "(cd backend && uv sync --group relax)."
        )
    if len(structure) > MAX_SITES:
        raise ToolError(f"Relaxation is limited to {MAX_SITES} sites.")
    optimizer = _optimizer()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = optimizer.relax(
            structure.copy(), fmax=FMAX, steps=MAX_STEPS, relax_cell=True, verbose=False
        )
    trajectory = result["trajectory"]
    final: Structure = result["final_structure"]
    max_force = float(np.linalg.norm(trajectory.forces[-1], axis=1).max())
    model_version = getattr(optimizer.calculator.model, "version", None) or "unknown"
    return RelaxOutcome(
        structure=final,
        steps=len(trajectory.energies),
        converged=max_force <= FMAX,
        energy_per_atom=float(trajectory.energies[-1]) / len(final),
        method=(
            f"CHGNet {model_version} pretrained ML potential (package {version('chgnet')}), "
            f"cell and positions relaxed, fmax {FMAX} eV/Å, at most {MAX_STEPS} steps"
        ),
    )


def displacement_summary(before: Structure, after: Structure) -> dict[str, Any]:
    """Lattice and volume change (fractions) and largest atom displacement (Å)."""
    delta = after.frac_coords - before.frac_coords
    delta -= np.round(delta)  # periodic images
    shifts = np.linalg.norm(after.lattice.get_cartesian_coords(delta), axis=1)
    return {
        "lattice_change": tuple(
            round(a1 / a0 - 1, 4)
            for a0, a1 in zip(before.lattice.abc, after.lattice.abc, strict=True)
        ),
        "volume_change": round(after.volume / before.volume - 1, 4),
        "max_displacement": round(float(shifts.max()), 3),
    }
