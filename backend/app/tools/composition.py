from importlib.metadata import version
from typing import Any

from pydantic import BaseModel, Field
from pymatgen.core import Composition

from app.tools.registry import Tool, ToolError

PYMATGEN_VERSION = version("pymatgen")
MAX_OXIDATION_GUESSES = 3


class CompositionArgs(BaseModel):
    formula: str = Field(
        min_length=1,
        max_length=100,
        description="Chemical formula, e.g. 'SrTiO3' or 'Sr0.5La0.5TiO3'.",
    )


def composition_info(args: CompositionArgs) -> dict[str, Any]:
    try:
        comp = Composition(args.formula)
    except (ValueError, KeyError) as exc:
        raise ToolError(f"Cannot parse formula {args.formula!r}: {exc}") from exc
    if comp.num_atoms == 0:
        raise ToolError(f"Formula {args.formula!r} has no atoms.")
    # Unknown symbols (e.g. "Xx") parse as dummy species instead of failing.
    if not comp.valid:
        raise ToolError(f"Formula {args.formula!r} contains symbols that are not elements.")

    guesses = comp.oxi_state_guesses()[:MAX_OXIDATION_GUESSES]
    return {
        "formula": args.formula,
        "reduced_formula": comp.reduced_formula,
        "elements": [str(el) for el in comp.elements],
        "atomic_fractions": {
            str(el): round(comp.get_atomic_fraction(el), 4) for el in comp.elements
        },
        "molar_mass": {"value": round(float(comp.weight), 3), "units": "g/mol"},
        "oxidation_state_guesses": [
            {el: round(state, 3) for el, state in guess.items()} for guess in guesses
        ],
        "charge_balanced": bool(guesses),
        "provenance": {
            "source": "pymatgen",
            "version": PYMATGEN_VERSION,
            "method": "Composition.oxi_state_guesses (common oxidation states, ICSD-based ranking)",
        },
    }


COMPOSITION_TOOL = Tool(
    name="composition_info",
    description=(
        "Parse a chemical formula and return its reduced formula, elements, atomic "
        "fractions, molar mass, and charge-balanced oxidation-state guesses. "
        "Use this for any composition or oxidation-state question."
    ),
    args_model=CompositionArgs,
    handler=composition_info,
)
