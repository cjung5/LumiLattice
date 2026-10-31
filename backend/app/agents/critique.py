"""Muse Spark structure critique: a reviewer's reading of one candidate.

Muse Spark gets (1) evidence items computed by the deterministic tools, each with an ID, and
(2) rendered views of the crystal structure. It returns a strict JSON critique. Every point
cites evidence IDs, and every decimal number in the text must appear in the evidence at the
precision written. If not, the model gets one retry; problems that remain are returned as
warnings with the critique. The critique is an opinion, never evidence.
"""

import json
import re
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agents.loop import BEGINNER_NOTE, LANGUAGES, Audience
from app.models.candidates import Candidate
from app.models.critique import Critique, CritiquePoint, CritiqueSuggestion, EvidenceItem
from app.models.evidence import PropertyValue
from app.tools.export import describe
from app.tools.goals import Goal, GoalScore
from app.tools.registry import ToolError
from app.tools.spatial import SpatialAnalysis

MAX_POINTS, MAX_SUGGESTIONS, MAX_QUESTIONS = 8, 3, 3
# Decimals only: integers also appear in formulas, counts, and IDs (SrTiO3, LL-0003).
NUMBER = re.compile(r"(?<![\w.])\d+\.\d+")


class View(BaseModel):
    """A rendered view of the structure, sent by the browser."""

    label: str = Field(max_length=80)  # e.g. "down the c axis"
    image: str = Field(max_length=3_000_000, pattern=r"^data:image/(png|jpeg);base64,")


SYSTEM_PROMPT = """You are a careful materials scientist reviewing one candidate material for \
an AR waveguide: high refractive index n near 550 nm, and a band gap wide enough to be \
transparent in the visible range. You get evidence items computed by deterministic tools, \
each with an ID, and rendered views of the candidate's crystal structure.

Rules:
- Cite the evidence IDs behind every point and suggestion. Use only IDs from the list.
- Do not write any number that is not in the evidence. Do not estimate new values.
- Heuristic values are ranges between end members, not predictions. Say so when you use one.
- You may describe what the images show (arrangement, layering, or clustering of the \
substituted atoms, tilts, distortions). Set basis to "image" (images only) or "both". The \
images show an ordered model, not a measurement.
- Be specific and critical. Prefer concerns the researcher can test.
- Be brief: a summary of at most 2 sentences, and points of 1 or 2 short sentences (about \
40 words). Cite the evidence by ID instead of repeating it; quote only the numbers that \
carry the argument.
- verdict: "promising", "mixed", "weak", or "insufficient_evidence" for this goal.
- At most {max_points} points, {max_suggestions} suggestions (a concrete change of element, \
site, or fraction, or a next check such as relaxation or a measurement), and \
{max_questions} questions for the researcher whose answers would change the assessment.
- Write all text in {language}. Keep chemical formulas, IDs, and units unchanged."""

_POINT = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["strength", "concern", "open_question"]},
        "text": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "basis": {"type": "string", "enum": ["evidence", "image", "both"]},
    },
    "required": ["kind", "text", "evidence", "basis"],
    "additionalProperties": False,
}
_SUGGESTION = {
    "type": "object",
    "properties": {
        "change": {"type": "string"},
        "rationale": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["change", "rationale", "evidence"],
    "additionalProperties": False,
}
OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["promising", "mixed", "weak", "insufficient_evidence"],
        },
        "summary": {"type": "string"},
        "points": {"type": "array", "items": _POINT},
        "suggestions": {"type": "array", "items": _SUGGESTION},
        "questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["verdict", "summary", "points", "suggestions", "questions"],
    "additionalProperties": False,
}


def _f(x: float, digits: int = 3) -> str:
    text = f"{x:.{digits}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _pv(pv: PropertyValue | None, unit: str = "") -> str:
    if pv is None or pv.status == "Unknown":
        return "unknown"
    if pv.value_range:
        lo, hi = pv.value_range
        return f"{_f(lo)}-{_f(hi)}{unit} ({pv.status} range)"
    if pv.value is not None:
        return f"{_f(pv.value)}{unit} ({pv.status})"
    return "unknown"


def _conditions(pv: PropertyValue | None) -> str:
    return f" {pv.conditions[:200]}" if pv and pv.conditions else ""


def _site_text(m: Any) -> str:
    parts = [
        f"{m.element}{m.index} ({m.element} {m.oxidation_state:+g}), CN {m.coordination}",
        f"mean bond {_f(m.mean_bond)} Å",
    ]
    if m.expected_bond is not None:
        parts.append(f"Shannon expected {_f(m.expected_bond)} Å")
    if m.size_mismatch is not None:
        parts.append(f"size mismatch {m.size_mismatch:+.1%}")
    if m.bvs is not None:
        parts.append(f"bond valence sum {_f(m.bvs, 2)}")
    if m.bvs_bond_change is not None:
        parts.append(f"bond change that would fix the BVS {m.bvs_bond_change:+.1%}")
    return "; ".join(parts)


def _spatial_items(sa: SpatialAnalysis, prefix: str, label: str) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    sym, before = sa.symmetry, sa.parent_symmetry
    text = f"{label}: space group {sym.spacegroup} ({sym.crystal_system}, {sym.optical_class})"
    if before:
        text += f"; reference {before.spacegroup} ({before.optical_class})"
    items.append(EvidenceItem(id=f"{prefix}symmetry", group="spatial", text=text + "."))
    parents = {p.index: p for p in sa.parent_polyhedra}
    for p in sa.polyhedra:
        text = f"{label}: {p.element}{p.index} {p.shape}, CN {p.coordination}, "
        text += f"distortion index {_f(p.distortion_index, 4)}"
        if p.index in parents:
            text += f" (reference {_f(parents[p.index].distortion_index, 4)})"
        if p.quadratic_elongation is not None:
            text += f", quadratic elongation {_f(p.quadratic_elongation, 4)}"
        if p.bond_angle_variance is not None:
            text += f", bond-angle variance {_f(p.bond_angle_variance, 2)} deg^2"
        items.append(
            EvidenceItem(id=f"{prefix}poly.{p.element}{p.index}", group="spatial", text=text)
        )
    links = sa.linkages
    text = (
        f"{label}: cation polyhedra share {links.corner} corners, {links.edge} edges, "
        f"{links.face} faces"
    )
    if links.bxb_angles:
        text += (
            f"; corner-shared B-X-B angles {_f(min(links.bxb_angles), 1)}-"
            f"{_f(max(links.bxb_angles), 1)} deg"
        )
    if links.mean_tilt is not None:
        text += f"; mean octahedral tilt {_f(links.mean_tilt, 1)} deg"
    items.append(EvidenceItem(id=f"{prefix}links", group="spatial", text=text + "."))
    for d in sa.dopants:
        text = f"{len(d.sites)} {d.element} in the cell"
        if d.shortest is not None and len(d.sites) == 1:
            # Not clustering: the only dopant's nearest copy is its own periodic image.
            text += (
                f"; its nearest {d.element} is its own periodic image at {_f(d.shortest, 2)} Å, "
                "a distance set by the cell size, not by clustering"
            )
        elif d.shortest is not None and d.periodic_chains:
            text += (
                f"; each {d.element} is nearest to its own periodic image at "
                f"{_f(d.shortest, 2)} Å (chains set by a cell one host cell thick, the same in "
                "every arrangement of this cell), not to another dopant"
            )
        elif d.shortest is not None:
            text += (
                f"; nearest {d.element}-{d.element} distance {_f(d.shortest, 2)} Å "
                f"(shortest possible on these sites {_f(d.cation_spacing, 2)} Å)"
            )
        items.append(
            EvidenceItem(id=f"{prefix}dopants.{d.element}", group="spatial", text=text + ".")
        )
    o = sa.ordering
    if o:
        cell = "x".join(str(n) for n in o.analysis_cell)
        if o.distinct == 1:
            text = (
                f"All {o.total} arrangements in a {cell} repeat have the same Ewald energy, so "
                "the point-charge model cannot rank them."
            )
        else:
            sample = f" (random sample of {len(o.energies)})" if o.truncated else ""
            text = (
                f"Ewald point-charge ranking of {o.total} arrangements in a {cell} repeat{sample}: "
                f"this arrangement ranks {o.chosen_rank} of {o.distinct} distinct energies, "
                f"{_f(o.chosen, 1)} meV/atom above the lowest. Ranking only."
            )
        items.append(EvidenceItem(id=f"{prefix}ordering", group="spatial", text=text))
    return items


def evidence_pack(
    candidate: Candidate,
    goal_score: GoalScore | None,
    spatial: SpatialAnalysis | None,
    relaxed_spatial: SpatialAnalysis | None,
) -> list[EvidenceItem]:
    items = [
        EvidenceItem(id=f"check.{c.id}", group="check", text=f"{c.name}: {c.status}. {c.message}")
        for c in candidate.assessment.checks
    ]
    items += [
        EvidenceItem(id=f"site.{m.element}{m.index}", group="site", text=_site_text(m))
        for m in candidate.assessment.site_metrics
    ]
    est = candidate.optical_estimate
    if est:
        items.append(
            EvidenceItem(
                id="optics.n",
                group="optics",
                text=f"Candidate n near 550 nm: {_pv(est.estimate)}.{_conditions(est.estimate)}",
            )
        )
        if est.band_gap:
            items.append(
                EvidenceItem(
                    id="optics.band_gap",
                    group="optics",
                    text=f"Candidate band gap: {_pv(est.band_gap, ' eV')}."
                    f"{_conditions(est.band_gap)}",
                )
            )
        if est.linear_mix:
            mix = est.linear_mix
            items.append(
                EvidenceItem(
                    id="optics.linear_mix",
                    group="optics",
                    text=(
                        f"Linear mix of end members: n {_f(mix.n) if mix.n is not None else 'unknown'}, "
                        f"band gap {_f(mix.band_gap) if mix.band_gap is not None else 'unknown'} eV. "
                        f"Typically off by about {_f(mix.typical_n_error)} (n) and "
                        f"{_f(mix.typical_gap_error_ev)} eV (gap). {mix.note}"
                    ),
                )
            )
        for m in est.end_members:
            items.append(
                EvidenceItem(
                    id=f"optics.{m.formula}",
                    group="optics",
                    text=f"End member {m.formula}: n {_pv(m.n)}; band gap {_pv(m.band_gap, ' eV')}.",
                )
            )
    if goal_score:
        items += [
            EvidenceItem(id=f"goal.{c.id}", group="goal", text=f"{c.verdict}: {c.detail}")
            for c in goal_score.criteria
        ]
    if spatial:
        items += _spatial_items(spatial, "spatial.", "Candidate")
    r = candidate.relaxation
    if r:
        change = ", ".join(f"{x:+.1%}" for x in r.lattice_change)
        items.append(
            EvidenceItem(
                id="relaxation",
                group="relaxation",
                text=(
                    f"{r.method}. Converged: {r.converged}, {r.steps} steps. Volume change "
                    f"{r.volume_change:+.1%}; a, b, c change {change}; largest atom shift "
                    f"{_f(r.max_displacement)} Å. Energies are from a machine-learned potential."
                ),
            )
        )
        unrelaxed = {c.id: c for c in candidate.assessment.checks}
        for c in r.assessment.checks:
            old = unrelaxed.get(c.id)
            if old is None or (old.status, old.message) != (c.status, c.message):
                items.append(
                    EvidenceItem(
                        id=f"relaxed.check.{c.id}",
                        group="check",
                        text=f"After relaxation, {c.name}: {c.status}. {c.message}",
                    )
                )
        items += [
            EvidenceItem(
                id=f"relaxed.site.{m.element}{m.index}",
                group="site",
                text="After relaxation, " + _site_text(m),
            )
            for m in r.assessment.site_metrics
        ]
    if relaxed_spatial:
        items += _spatial_items(relaxed_spatial, "relaxed.spatial.", "After relaxation")
    for i, e in enumerate(candidate.experiments, 1):
        unit = " eV" if e.property == "band_gap" else ""
        at = f" at {_f(e.wavelength_nm, 1)} nm" if e.wavelength_nm else ""
        method = f", {e.method}" if e.method else ""
        items.append(
            EvidenceItem(
                id=f"measurement.{i}",
                group="measurement",
                text=(
                    f"Researcher's measurement: {e.property.replace('_', ' ')} = "
                    f"{_f(e.value)}{unit}{at} ({e.sample}{method}); reference "
                    f"{e.reference or 'none'}. Not verified by LumiLattice."
                ),
            )
        )
    return items


def header(
    candidate: Candidate,
    goal: Goal,
    views: list[View],
    legend: dict[str, str],
    geometry: Literal["unrelaxed", "relaxed"],
) -> str:
    t = candidate.transformation
    host = f"{t.host.source} {t.host.reference or ''}".strip()
    lines = [
        (
            f"Candidate {candidate.candidate_id}: {candidate.formula}, made from {t.root_formula} "
            f"({host}) by {describe(t.lineage)}; supercell {'x'.join(map(str, t.supercell))} of "
            f"the host cell, {len(candidate.structure.sites)} atoms; structural assessment "
            f"{candidate.assessment.status}."
        ),
        f"Goal: n >= {_f(goal.target_n)} near 550 nm and band gap >= {_f(goal.min_band_gap)} eV"
        + (
            f"; forbidden elements {', '.join(goal.forbidden_elements)}."
            if goal.forbidden_elements
            else "."
        ),
    ]
    if views:
        colors = ", ".join(f"{el} {color}" for el, color in sorted(legend.items()))
        lines.append(
            f"Images: {len(views)} rendered views of the {geometry} cell "
            f"({'; '.join(v.label for v in views)}). Element colors: {colors}. Substituted "
            "atoms are drawn larger and labeled with their site IDs (for example La0). The box "
            "is the cell. Atoms on a cell face, edge, or corner are drawn again on the opposite "
            "side, so the images show more atoms than the cell has. The images show an ordered "
            "model, not a measurement."
        )
    else:
        lines.append("No images: the structure views could not be captured.")
    return "\n".join(lines)


def known_numbers(texts: list[str]) -> list[float]:
    return [float(token) for text in texts for token in NUMBER.findall(text)]


def unsupported_numbers(text: str, known: list[float]) -> list[str]:
    """Decimal numbers in text that match no evidence number at the precision written."""
    missing = []
    for token in NUMBER.findall(text):
        tolerance = 0.5 * 10 ** -len(token.split(".")[1]) + 1e-9
        if not any(abs(float(token) - k) <= tolerance for k in known):
            missing.append(token)
    return missing


def problems(raw: dict[str, Any], ids: set[str], known: list[float]) -> list[str]:
    issues: list[str] = []

    def numbers(where: str, text: str) -> None:
        if bad := unsupported_numbers(text, known):
            issues.append(f"{where} has numbers that are not in the evidence: {', '.join(bad)}")

    numbers("summary", raw["summary"])
    for i, p in enumerate(raw["points"][:MAX_POINTS], 1):
        unknown = [e for e in p["evidence"] if e not in ids]
        if unknown:
            issues.append(f"point {i} cites unknown IDs: {', '.join(unknown)}")
        if p["basis"] != "image" and not any(e in ids for e in p["evidence"]):
            issues.append(f"point {i} cites no evidence (cite IDs, or set basis to image)")
        numbers(f"point {i}", p["text"])
    for i, s in enumerate(raw["suggestions"][:MAX_SUGGESTIONS], 1):
        unknown = [e for e in s["evidence"] if e not in ids]
        if unknown:
            issues.append(f"suggestion {i} cites unknown IDs: {', '.join(unknown)}")
        numbers(f"suggestion {i}", f"{s['change']} {s['rationale']}")
    for i, q in enumerate(raw["questions"][:MAX_QUESTIONS], 1):
        numbers(f"question {i}", q)
    return issues


def run_critique(
    client: Any,
    model: str,
    candidate: Candidate,
    goal: Goal,
    evidence: list[EvidenceItem],
    views: list[View],
    legend: dict[str, str],
    geometry: Literal["unrelaxed", "relaxed"],
    locale: str = "en",
    audience: Audience = "expert",
) -> Critique:
    intro = header(candidate, goal, views, legend, geometry)
    listing = "\n".join(f"{e.id} | {e.text}" for e in evidence)
    content: list[dict[str, Any]] = [
        {"type": "text", "text": f"{intro}\n\nEvidence (ID | fact):\n{listing}"}
    ]
    for v in views:
        content.append({"type": "text", "text": f"View: {v.label}"})
        content.append({"type": "image_url", "image_url": {"url": v.image}})
    system = SYSTEM_PROMPT.format(
        language=LANGUAGES.get(locale, "English"),
        max_points=MAX_POINTS,
        max_suggestions=MAX_SUGGESTIONS,
        max_questions=MAX_QUESTIONS,
    )
    if audience == "beginner":
        system += "\n- " + BEGINNER_NOTE
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": content},
    ]
    ids = {e.id for e in evidence}
    known = known_numbers([intro, *(e.text for e in evidence)])

    raw: dict[str, Any] = {}
    issues: list[str] = []
    for _ in range(2):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "critique", "schema": OUTPUT_SCHEMA, "strict": True},
            },
            max_completion_tokens=12000,
        )
        text = response.choices[0].message.content
        if not text:
            raise ToolError("Muse Spark returned no critique. Try again.")
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ToolError("Muse Spark returned a critique that is not valid JSON.") from exc
        issues = problems(raw, ids, known)
        if not issues:
            break
        messages += [
            {"role": "assistant", "content": text},
            {
                "role": "user",
                "content": "Fix these problems and return the full JSON: " + "; ".join(issues[:12]),
            },
        ]

    def cited(found: list[str]) -> list[str]:
        return [e for e in dict.fromkeys(found) if e in ids]

    return Critique(
        created_at=datetime.now(UTC),
        model=model,
        locale=locale,
        geometry=geometry,
        views=len(views),
        verdict=raw["verdict"],
        summary=raw["summary"],
        points=[
            CritiquePoint(
                kind=p["kind"], text=p["text"], evidence=cited(p["evidence"]), basis=p["basis"]
            )
            for p in raw["points"][:MAX_POINTS]
        ],
        suggestions=[
            CritiqueSuggestion(
                change=s["change"], rationale=s["rationale"], evidence=cited(s["evidence"])
            )
            for s in raw["suggestions"][:MAX_SUGGESTIONS]
        ],
        questions=raw["questions"][:MAX_QUESTIONS],
        evidence=evidence,
        warnings=issues,
    )
