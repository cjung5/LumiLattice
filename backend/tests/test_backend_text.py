"""Every sentence the backend shows must have a template in frontend/messages/en.json.

The frontend (lib/backendText.ts) translates backend sentences by these templates, and a sentence
with no template stays in English. This test uses the same matching rules.
"""

import json
import re
from pathlib import Path

import pytest
from pymatgen.core import Lattice, Structure

from app.models.candidates import Substitution
from app.models.evidence import Provenance
from app.storage.memory import MemoryStore
from app.tools import novelty, scorecard, spatial, substitution, validation
from app.tools.candidates import create_candidate
from app.tools.goals import Goal, score_candidate, score_formula
from app.tools.materials import to_record
from app.tools.reference_db import get_reference_db
from app.tools.spatial import analyze, before_substitution
from app.tools.validation import assess

MESSAGES = Path(__file__).resolve().parents[2] / "frontend" / "messages"
ENGLISH = json.loads((MESSAGES / "en.json").read_text())["Backend"]
SENTENCE = re.compile(r"(?<=[.)])\s+(?=[A-Z])")
PLACEHOLDER = re.compile(r"\{\w+\}")


def _patterns() -> list[re.Pattern]:
    patterns = []
    for text in ENGLISH["templates"].values():
        pieces = PLACEHOLDER.split(text)
        patterns.append(re.compile("(.+?)".join(re.escape(p) for p in pieces) + r"\Z"))
    return patterns


PATTERNS = _patterns()
WORDS = set(ENGLISH["words"].values())


def _known(text: str) -> bool:
    return text in WORDS or any(p.match(text) for p in PATTERNS)


def untranslated(text: str) -> list[str]:
    return [part for part in SENTENCE.split(text) if not _known(part)]


def test_no_template_crosses_a_sentence_boundary():
    assert [t for t in ENGLISH["templates"].values() if SENTENCE.search(t)] == []


def test_a_placeholder_cannot_swallow_the_next_sentence():
    text = "Ordered model: biaxial. Host: isotropic. This sentence has no template."
    assert untranslated(text) == ["This sentence has no template."]


def collect(candidate, structure) -> list[str]:
    """Every backend sentence the panels show for one candidate."""
    a = candidate.assessment
    texts = [a.status, *a.notes]
    for check in a.checks:
        texts += [check.name, check.message]
        if check.method:
            texts.append(check.method)
    texts.append(candidate.transformation.site_selection)
    optical = candidate.optical_estimate
    if optical:
        for pv in (optical.estimate, optical.band_gap):
            if pv and pv.conditions:
                texts.append(pv.conditions)
        for m in optical.end_members:
            texts += [m.n.conditions or "", (m.band_gap.conditions or "") if m.band_gap else ""]
        if optical.linear_mix:
            texts.append(optical.linear_mix.note)
    parent = before_substitution(structure, candidate.transformation)
    goal = Goal()
    db = get_reference_db()
    texts += [c.detail for c in score_candidate(candidate, goal).criteria]
    card = scorecard.build_scorecard(candidate, structure, parent, goal, db)
    texts += [card.method, card.benchmark.note]
    for metric in card.metrics:
        texts.append(metric.detail)
        if metric.id == "isotropy" and metric.value:
            texts.append(metric.value)
    replaced = candidate.transformation.substituted_sites
    focus = sorted(i for sites in replaced.values() for i in sites)
    result = analyze(structure, focus, parent, replaced)
    texts += [*result.findings, *result.notes]
    if result.ordering:
        texts.append(result.ordering.method)
    texts += [p.shape for p in result.polyhedra if not p.shape.endswith("-coordinate")]
    return [t for t in texts if t]


def make(host: Structure, old: str, new: str, fraction: float, **kwargs):
    store = MemoryStore()
    candidate = create_candidate(
        store,
        host,
        Provenance(source="test"),
        [Substitution(element_from=old, element_to=new, fraction=fraction)],
        **kwargs,
    )
    return store.get(candidate.candidate_id)


CASES = {
    "partial": lambda h: make(h, "Sr", "Ba", 0.5),
    "lowest_ewald": lambda h: make(h, "Sr", "Ba", 0.5, arrangement="lowest_ewald"),
    "full": lambda h: make(h, "Sr", "Ba", 1),
    "charge_fail": lambda h: make(h, "Sr", "Cs", 1),
    "too_small": lambda h: make(h, "Sr", "Mg", 1),
    "mixed_valence": lambda h: make(h, "Ti", "Mn", 0.5),
    "wrong_size_b": lambda h: make(h, "Ti", "Na", 0.5),
}


@pytest.mark.parametrize("case", CASES)
def test_candidate_sentences_have_templates(srtio3, case):
    if not get_reference_db().available:
        pytest.skip("reference.sqlite is not built")
    candidate, structure = CASES[case](srtio3)

    missing = [m for text in collect(candidate, structure) for m in untranslated(text)]
    assert missing == []


def test_co_substitution_has_templates(srtio3):
    store = MemoryStore()
    candidate = create_candidate(
        store,
        srtio3,
        Provenance(source="test"),
        [
            Substitution(element_from="Sr", element_to="La", fraction=0.25),
            Substitution(element_from="Ti", element_to="Al", fraction=0.25),
        ],
    )
    structure = store.get(candidate.candidate_id)[1]
    assert [m for t in collect(candidate, structure) for m in untranslated(t)] == []


def test_reference_sentences_have_templates():
    db = get_reference_db()
    if not db.available:
        pytest.skip("reference.sqlite is not built")
    texts = list(db.landscape().notes) + [db.reference("SrTiO3").note]
    for formula in ("SrTiO3", "TiO2", "LaAlO3", "CaTiO3", "BaSr3Ti4O12", "Pb9Xe"):
        n, gap = db.best_n(formula), db.best_gap(formula)
        texts += [n.conditions or "", gap.conditions or ""]
        texts += [c.detail for c in score_formula(formula, Goal(), db).criteria]
    assert [m for t in texts if t for m in untranslated(t)] == []


def test_materials_project_sentences_have_templates():
    record = to_record({"material_id": "mp-1", "n": 2.0, "band_gap": 3.0, "energy_above_hull": 0})
    values = (record.refractive_index, record.band_gap, record.energy_above_hull)
    texts = [v.conditions for v in values] + [record.band_gap.provenance.method]
    assert [m for t in texts for m in untranslated(t)] == []


def test_fixed_notes_and_errors_have_templates():
    texts = [
        validation.NO_RELAXATION_NOTE,
        validation.RELAXED_NOTE,
        novelty.CAVEAT,
        substitution.SITE_SELECTION,
        "Sr is not in the host (Ba, O, Ti).",
        "'Xx' is not an element symbol.",
        "Substituting Sr with itself does nothing.",
        "Fractions for Sr add up to 1.50, more than 1.",
    ]
    assert [m for t in texts for m in untranslated(t)] == []


def test_metal_host_sentences_have_templates():
    copper = Structure.from_spacegroup("Fm-3m", Lattice.cubic(3.61), ["Cu"], [[0, 0, 0]])
    assessment = assess(copper)
    texts = [
        assessment.status,
        *(c.message for c in assessment.checks),
        *(c.name for c in assessment.checks),
    ]
    assert [m for t in texts for m in untranslated(t)] == []
    result = spatial.analyze(copper)
    assert [m for t in [*result.findings, *result.notes] for m in untranslated(t)] == []


@pytest.mark.parametrize("locale", ["ko", "zh-Hans", "ja", "es", "de"])
def test_every_template_is_translated_with_its_placeholders(locale):
    target = json.loads((MESSAGES / f"{locale}.json").read_text()).get("Backend")
    assert target is not None
    for key, text in ENGLISH["templates"].items():
        assert key in target["templates"], key
        assert set(PLACEHOLDER.findall(text)) == set(
            PLACEHOLDER.findall(target["templates"][key])
        ), key
