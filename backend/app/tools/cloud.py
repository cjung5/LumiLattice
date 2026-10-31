"""A model of each atom's electron cloud, for the 3D cloud view. Not a computed electron density.

Each atom gets a soft Gaussian cloud. Its size comes from the ionic radius (Shannon 1976), and it
stretches along the atom's bonds, weighted by bond valence (O'Keeffe & Brese 1991). So the picture
shows geometry the app already has: large anions, small cations, and which way the bonds pull. A
real density needs a DFT calculation, which candidates do not have.
"""

import math
from typing import Literal

import numpy as np
from pydantic import BaseModel
from pymatgen.core import Element, Structure

from app.tools.ionic import BV_B, anion_shell, ionic_model, shannon_radius, universal_r0

SIZE_FROM_RADIUS = 0.42  # Gaussian width as a share of the ionic radius
STRETCH = 0.6  # 0: every cloud is round; 1: a cloud is flat across its bonds
DEFAULT_RADIUS = 1.2  # Å, when no radius is tabulated


class CloudSite(BaseModel):
    index: int
    element: str
    frac: tuple[float, float, float]
    radius: float  # Å
    # Gaussian covariance in Å²: xx, yy, zz, xy, xz, yz
    covariance: tuple[float, float, float, float, float, float]
    direction: tuple[float, float, float]  # unit vector of the longest axis, Cartesian
    stretch: float  # 0: round; 1: a rod along `direction`


class CloudModel(BaseModel):
    lattice: tuple[
        tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]
    ]  # rows: a, b, c in Å
    kind: Literal["ionic", "neutral"]  # neutral: no anion, so no bonds to stretch along
    sites: list[CloudSite]


def _bond_weight(cation: str, anion: str, distance: float) -> float:
    try:
        return math.exp((universal_r0(Element(cation), Element(anion)) - distance) / BV_B)
    except (KeyError, ValueError):
        return 1 / distance  # no bond-valence parameters: nearer bonds still count for more


def _site(
    index: int, structure: Structure, radius: float, tensor: np.ndarray, weight: float
) -> CloudSite:
    site = structure[index]
    sigma2 = (SIZE_FROM_RADIUS * radius) ** 2
    if weight > 0:
        shape = tensor / weight  # trace 1
        values, vectors = np.linalg.eigh(shape)
        stretch = float(values[-1] - values[0])
        direction = vectors[:, -1]
        # One sign per axis, so that neighboring clouds do not cancel when blended.
        if direction[np.argmax(np.abs(direction))] < 0:
            direction = -direction
        covariance = sigma2 * ((1 - STRETCH) * np.eye(3) + 3 * STRETCH * shape)
    else:
        stretch, direction = 0.0, np.array([0.0, 0.0, 1.0])
        covariance = sigma2 * np.eye(3)
    c = covariance
    return CloudSite(
        index=index,
        element=site.specie.symbol,
        frac=tuple(round(float(x), 5) for x in site.frac_coords),
        radius=round(radius, 3),
        covariance=tuple(
            round(float(v), 4) for v in (c[0, 0], c[1, 1], c[2, 2], c[0, 1], c[0, 2], c[1, 2])
        ),
        direction=tuple(round(float(x), 4) for x in direction),
        stretch=round(stretch, 3),
    )


def cloud_model(structure: Structure) -> CloudModel:
    lattice = tuple(tuple(round(float(x), 5) for x in row) for row in structure.lattice.matrix)
    size = len(structure)
    model = ionic_model(structure)
    if model is None:
        sites = [
            _site(
                i, structure, float(s.specie.atomic_radius or DEFAULT_RADIUS), np.zeros((3, 3)), 0
            )
            for i, s in enumerate(structure)
        ]
        return CloudModel(lattice=lattice, kind="neutral", sites=sites)

    tensors = np.zeros((size, 3, 3))
    weights = np.zeros(size)
    bonds = np.zeros(size, dtype=int)
    for i, site in enumerate(structure):
        symbol = site.specie.symbol
        if model.is_anion(symbol):
            continue
        for neighbor in anion_shell(structure, i, model):
            weight = _bond_weight(symbol, neighbor.specie.symbol, neighbor.nn_distance)
            unit = (neighbor.coords - site.coords) / neighbor.nn_distance
            outer = weight * np.outer(unit, unit)
            # The same bond stretches both of its atoms.
            for j in (i, neighbor.index):
                tensors[j] += outer
                weights[j] += weight
                bonds[j] += 1

    sites = []
    for i, site in enumerate(structure):
        symbol = site.specie.symbol
        found = shannon_radius(symbol, model.oxidation_states[symbol], int(bonds[i]) or 6)
        radius = found[0] if found else float(site.specie.atomic_radius or DEFAULT_RADIUS)
        sites.append(_site(i, structure, radius, tensors[i], float(weights[i])))
    return CloudModel(lattice=lattice, kind="ionic", sites=sites)
