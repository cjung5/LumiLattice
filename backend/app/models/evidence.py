"""Scientific output policy (spec sections 3.4 and 6).

Every property the app shows carries its provenance and one of four evidence tags.
"""

from typing import Literal

from pydantic import BaseModel

EvidenceStatus = Literal["Experimental", "DFT-computed", "Heuristic", "Unknown"]


class Provenance(BaseModel):
    source: str  # e.g. "Materials Project", "pymatgen"
    method: str | None = None  # e.g. "GGA+U", "n = sqrt(eps_inf)"
    version: str | None = None
    reference: str | None = None  # DOI, URL, or database ID


class PropertyValue(BaseModel):
    name: str
    value: float | None = None
    # Heuristic values are shown as a range only, never as a single number.
    value_range: tuple[float, float] | None = None
    units: str | None = None
    status: EvidenceStatus = "Unknown"
    conditions: str | None = None  # e.g. "long-wavelength limit, not n(550 nm)"
    provenance: Provenance | None = None
