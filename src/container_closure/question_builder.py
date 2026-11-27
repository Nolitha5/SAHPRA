"""
QuestionBuilder for the S.6 Container Closure Agent (Phase 5b).

Implements container_closure.evaluator.QuestionBuilder:
    Callable[[S6Claim], Sequence[RegulatoryQuestion]]

Responsibility
--------------
Build natural-language RegulatoryQuestion objects from one validated
S6Claim's own context, organised around S6's five named assessment
objectives (container description, closure components, compatibility,
protection and integrity, storage statements). This module decides
WHICH topics are worth asking M2 about for a given claim -- it never
decides whether a requirement exists, whether a passage is applicable,
or whether a claim complies with anything. Asking a question is not a
regulatory assertion.

What this is NOT
-----------------
* Not a regulatory requirement list. The five objective labels are
  question-preparation categories (per the approved design), not a
  claim that a requirement exists for each one.
* Not a source-category or compliance judgement of any kind.
* Not a direct call to M2. This module only constructs
  RegulatoryQuestion values; container_closure.evaluator.run_evaluation
  (via the injected RegulatoryEvidenceSource, owned and orchestrated by
  M1) is the only thing that ever submits them anywhere.

Trigger heuristic
-----------------
Each objective is triggered by a small, explicit, documented set of
topic-routing terms checked against the claim's own text, packaging
components, and quantitative-value keys. This is a transparent,
engineering-level routing heuristic for deciding which questions to
ask -- it is NOT a pharmacist-approved classification of what S.6
requires, carries no regulatory authority, and never feeds into any
compliance decision. A claim that triggers no objective yields an
empty question list, which run_evaluation already treats as a valid
"no_topics_selected" outcome.

Provenance
----------
RegulatoryQuestion has no free-form claim_id/provenance field (its
dataclass shape is fixed by evaluator.py and is not changed here), so
each generated question's own `question` text embeds the originating
claim's claim_id and verbatim text, giving every question full,
human- and audit-readable traceability back to the claim that produced
it without needing any evaluator.py change.
"""
from __future__ import annotations

from shared.models import S6Claim

from container_closure.evaluator import RegulatoryQuestion

# ---------------------------------------------------------------------------
# Topic-routing terms (engineering heuristic only -- see module docstring)
# ---------------------------------------------------------------------------

_CONTAINER_TERMS = ("container", "vial", "bottle", "ampoule", "ampule", "syringe", "cartridge", "bag", "pouch")
_CLOSURE_TERMS = ("closure", "stopper", "cap", "seal", "liner", "crimp", "plunger")
_COMPATIBILITY_TERMS = ("extractable", "leachable", "compatib", "interaction", "adsorption", "sorption")
_STORAGE_TERMS = (
    "storage", "stability", "shelf life", "shelf-life", "accelerated",
    "long-term", "long term", "refrigerat", "room temperature",
)
_INTEGRITY_TERMS = ("integrity", "tamper", "moisture", "light protection", "light-protect", "permeation", "leak")

_OBJECTIVE_PHRASING: dict[str, str] = {
    "container_description": "what does the applicable guidance require regarding the container description",
    "closure_components": "what does the applicable guidance require regarding the closure components",
    "compatibility": "what does the applicable guidance require regarding container/closure compatibility",
    "protection_and_integrity": "what does the applicable guidance require regarding container closure protection and integrity",
    "storage_statements": "what does the applicable guidance require regarding storage statements for this packaging",
}


def _claim_signal_text(claim: S6Claim) -> str:
    """Concatenation of every claim field that might carry a
    topic-routing signal, lower-cased once for repeated substring
    checks. Never used for anything beyond deciding which questions to
    ask."""
    parts = [
        claim.text,
        " ".join(claim.packaging_components),
        " ".join(claim.quantitative_values.keys()),
        " ".join(str(v) for v in claim.quantitative_values.values()),
    ]
    return " ".join(parts).lower()


def _triggered_objectives(claim: S6Claim) -> list[str]:
    signal = _claim_signal_text(claim)
    objectives: list[str] = []

    if claim.packaging_components or any(term in signal for term in _CONTAINER_TERMS):
        objectives.append("container_description")
    if any(term in signal for term in _CLOSURE_TERMS):
        objectives.append("closure_components")
    if any(term in signal for term in _COMPATIBILITY_TERMS):
        objectives.append("compatibility")
    if any(term in signal for term in _INTEGRITY_TERMS):
        objectives.append("protection_and_integrity")
    if claim.dates or any(term in signal for term in _STORAGE_TERMS):
        objectives.append("storage_statements")

    return objectives


def _build_question_text(claim: S6Claim, objective: str) -> str:
    phrasing = _OBJECTIVE_PHRASING[objective]
    return f'[claim_id={claim.claim_id}] For the S.6 packaging claim "{claim.text}", {phrasing}?'


def build_regulatory_questions(claim: S6Claim) -> list[RegulatoryQuestion]:
    """QuestionBuilder implementation.

    Returns one RegulatoryQuestion per triggered objective, or an
    empty list if the claim's own context triggers none. Never raises
    for a structurally valid S6Claim; never invents an objective the
    claim's own fields give no signal for."""
    return [
        RegulatoryQuestion(
            question=_build_question_text(claim, objective),
            assessment_objective=objective,
        )
        for objective in _triggered_objectives(claim)
    ]
