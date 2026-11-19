"""
S.6 / S.7 stability linker -- Phase 4b (controlling specification: design v11).

Purpose
-------
Deterministically link S.6 packaging claims (S6Claim) to S.7 stability
conditions (S7StabilityCondition) using only the fields already present
on the shared models.  The linker establishes *relatedness evidence*; it
never produces a regulatory verdict, never asserts a contradiction, and
never calls an LLM or external service.

Evidence model
--------------
Three signals are evaluated for every (claim, condition) pair:

* Signal A  ``batch_number``         S6Claim.batch_numbers        vs S7StabilityCondition.batch_number
* Signal B  ``packaging_reference``  S6Claim.packaging_components vs S7StabilityCondition.packaging_reference
* Signal C  ``container_reference``  S6Claim.packaging_components vs S7StabilityCondition.container_reference

Each signal takes exactly one of four outcomes: STRONG_POSITIVE,
WEAK_POSITIVE, DIVERGENT or ABSENT.  Signals B and C share their
claim-side source and are therefore not independent evidence.

Packaging text is normalised with an explicit ASCII-only contract
(see ``normalise_packaging``) and tokens fall into four categories:
generic packaging words, connector words, known material descriptors,
and unclassified tokens.  Generic and connector tokens never carry
evidence on their own.  Only an exact (connector-free, order-free,
duplicate-preserving) token-sequence match yields STRONG_POSITIVE, and
a pair in which either original string contains any non-ASCII
character can never reach STRONG_POSITIVE (the non-ASCII safeguard).

Classification (evaluated in order, first match wins)
-----------------------------------------------------
R1  all three signals ABSENT                                   -> INSUFFICIENT_DATA
R2  A strong AND (B strong OR C strong) AND no DIVERGENT       -> CONFIRMED_MATCH
R3  no DIVERGENT AND at least one STRONG                       -> POSSIBLE_MATCH
R4  all three DIVERGENT (no positive of any kind)              -> NO_MATCH
R5  otherwise                                                  -> UNCERTAIN_COMPARISON

Over the 64 possible signal-outcome combinations the distribution is
R1=1, R2=5, R3=14, R4=1, R5=43.

There is deliberately no POTENTIAL_CONFLICT classification and no
material-incompatibility inference.  Differences are preserved for
downstream review (divergent signals, unclassified tokens, per-component
notes) without being interpreted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence

from shared.models import S6Claim, S7StabilityCondition, SourceReference


# ---------------------------------------------------------------------------
# Signal names and outcomes
# ---------------------------------------------------------------------------

SIGNAL_BATCH = "batch_number"
SIGNAL_PACKAGING = "packaging_reference"
SIGNAL_CONTAINER = "container_reference"
ALL_SIGNALS: tuple[str, str, str] = (SIGNAL_BATCH, SIGNAL_PACKAGING, SIGNAL_CONTAINER)


class SignalOutcome(str, Enum):
    STRONG_POSITIVE = "strong_positive"
    WEAK_POSITIVE = "weak_positive"
    DIVERGENT = "divergent"
    ABSENT = "absent"


# Ranking used by the best-of-N component comparison (higher is better).
_OUTCOME_RANK: dict[SignalOutcome, int] = {
    SignalOutcome.STRONG_POSITIVE: 3,
    SignalOutcome.WEAK_POSITIVE: 2,
    SignalOutcome.DIVERGENT: 1,
    SignalOutcome.ABSENT: 0,
}


class LinkClassification(str, Enum):
    CONFIRMED_MATCH = "CONFIRMED_MATCH"
    POSSIBLE_MATCH = "POSSIBLE_MATCH"
    UNCERTAIN_COMPARISON = "UNCERTAIN_COMPARISON"
    NO_MATCH = "NO_MATCH"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


# Insufficient-data reasons, in precedence order (first applicable wins).
REASON_NO_CONDITIONS = "no_conditions_provided"
REASON_NO_LINKABLE_FIELDS = "no_linkable_fields"
REASON_ALL_PAIRS_INSUFFICIENT = "all_pairs_insufficient"


# ---------------------------------------------------------------------------
# Token vocabularies (closed, explicit, disjoint)
# ---------------------------------------------------------------------------

#: Non-discriminating category / component-type / form words.  A shared
#: generic token establishes nothing on its own; generic tokens do take
#: part in the exact-match sequence once both sides have meaningful content.
_GENERIC_PACKAGING_TOKENS: frozenset[str] = frozenset({
    "bottle", "vial", "cap", "closure", "container",
    "pack", "package", "packaging", "seal", "sealing",
    "stopper", "tube", "bag", "pouch", "blister",
    "ampoule", "ampule", "syringe", "cartridge",
    "liner", "insert", "tray", "wrap",
    "tubing", "membrane", "film",
})

#: Non-evidentiary English connector words.  Closed set; a word is added
#: only if it can never denote a component, material, grade, size or
#: identifier.  Connector tokens are excluded from meaningful tokens AND
#: from the exact-match sequence.
_CONNECTOR_TOKENS: frozenset[str] = frozenset({
    "with", "and", "or", "of", "in", "on", "for", "to",
    "the", "a", "an", "per", "plus", "without",
})

#: Recognised material descriptors.  A shared material token is weak
#: evidence only; it never proves component identity.  ``pet`` and ``pp``
#: are ambiguous abbreviations and are retained with that caveat.
#: ``silicon`` and ``teflon`` are deliberately excluded (unclassified).
_KNOWN_MATERIAL_TOKENS: frozenset[str] = frozenset({
    "glass", "plastic", "rubber", "metal",
    "aluminium", "aluminum", "steel", "stainless", "tin",
    "foil",
    "polypropylene", "polyethylene", "polycarbonate", "polyester", "nylon",
    "fluoropolymer",
    "hdpe", "ldpe", "pvc", "pp", "pet",
    "paper", "paperboard", "cardboard",
    "bromobutyl", "chlorobutyl", "butyl", "silicone",
    "borosilicate",
})

assert not (_GENERIC_PACKAGING_TOKENS & _CONNECTOR_TOKENS)
assert not (_GENERIC_PACKAGING_TOKENS & _KNOWN_MATERIAL_TOKENS)
assert not (_CONNECTOR_TOKENS & _KNOWN_MATERIAL_TOKENS)


# ---------------------------------------------------------------------------
# Normalisation (ASCII-only, explicit contract)
# ---------------------------------------------------------------------------


def _is_ascii_lower(c: str) -> bool:
    return "a" <= c <= "z"


def _is_ascii_digit(c: str) -> bool:
    return "0" <= c <= "9"


def contains_non_ascii(text: str | None) -> bool:
    """True when ``text`` contains any code point above U+007F.

    Evaluated on the ORIGINAL string before any transformation.  No
    exceptions: accented letters, other scripts, symbols and U+00A0 all
    count.  This is the trigger for the pair-level non-ASCII safeguard.
    """
    return text is not None and any(ord(ch) > 127 for ch in text)


def normalise_packaging(text: str | None) -> list[str]:
    """Normalise a packaging description into a list of ASCII tokens.

    Contract
    --------
    1. ``None`` -> ``[]``.
    2. Lowercase.
    3. Walk the lowercased string.  ASCII ``a-z`` / ``0-9`` are emitted.
       ``-`` and ``.`` are emitted only when ``0 < i < len-1`` and BOTH
       neighbours are ASCII digits (``10-20``, ``10.5``); otherwise they
       become a space.  Every other character -- whitespace, all other
       ASCII punctuation, every non-ASCII character -- becomes a space.
       There is no removal class, so two tokens can never be joined.
    4. ``str.split()`` (collapses runs, strips ends).

    ``str.isalnum`` / ``isdigit`` / ``isalpha`` are not used: they accept
    non-ASCII characters outside this contract.
    """
    if text is None:
        return []
    s = text.lower()
    n = len(s)
    out: list[str] = []
    for i in range(n):
        c = s[i]
        if _is_ascii_lower(c) or _is_ascii_digit(c):
            out.append(c)
        elif c == "-" or c == ".":
            has_both_neighbours = (i > 0) and (i < n - 1)
            if (
                has_both_neighbours
                and _is_ascii_digit(s[i - 1])
                and _is_ascii_digit(s[i + 1])
            ):
                out.append(c)
            else:
                out.append(" ")
        else:
            out.append(" ")
    return "".join(out).split()


def _meaningful(tokens: list[str]) -> list[str]:
    return [
        t for t in tokens
        if t not in _GENERIC_PACKAGING_TOKENS and t not in _CONNECTOR_TOKENS
    ]


def _evidentiary(tokens: list[str]) -> tuple[str, ...]:
    """Sorted, connector-free, duplicate-preserving token sequence used
    for the exact-match test (generic tokens are kept)."""
    return tuple(sorted(t for t in tokens if t not in _CONNECTOR_TOKENS))


def _unclassified(meaningful: list[str]) -> tuple[str, ...]:
    return tuple(sorted({t for t in meaningful if t not in _KNOWN_MATERIAL_TOKENS}))


def _connectors(tokens: list[str]) -> tuple[str, ...]:
    return tuple(sorted({t for t in tokens if t in _CONNECTOR_TOKENS}))


# ---------------------------------------------------------------------------
# Output dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ComponentMatchNote:
    """Per-component comparison detail for one packaging signal.

    All fields are ``str``, ``tuple[str, ...]`` or ``bool``, so instances
    are both immutable and hashable.
    """

    component_text: str
    signal_outcome: str  # SignalOutcome value
    shared_material_tokens: tuple[str, ...]
    unclassified_tokens_claim: tuple[str, ...]
    unclassified_tokens_condition: tuple[str, ...]
    non_ascii_safeguard_applied: bool


@dataclass(frozen=True)
class ClaimConditionLink:
    """One emitted (claim, condition) link.

    ``frozen=True`` guarantees that the fields of this dataclass cannot be
    reassigned after construction.  It does NOT make the nested
    ``SourceReference`` objects immutable and it does NOT guarantee that
    instances are hashable; both depend on the shared ``SourceReference``
    model, which this phase does not modify.  Do not use a
    ``ClaimConditionLink`` as a dict key or set member without first
    confirming ``SourceReference`` hashability separately.
    """

    claim_id: str
    condition_id: str
    classification: LinkClassification
    strong_signals: tuple[str, ...]
    weak_signals: tuple[str, ...]
    divergent_signals: tuple[str, ...]
    absent_signals: tuple[str, ...]
    claim_source_ref: SourceReference
    condition_source_ref: SourceReference
    component_notes_b: tuple[ComponentMatchNote, ...]
    component_notes_c: tuple[ComponentMatchNote, ...]
    notes: str


@dataclass
class LinkerSummary:
    # Claim accounting -- five mutually exclusive categories, sum == total_claims.
    confirmed_claim_ids: list[str] = field(default_factory=list)
    possible_claim_ids: list[str] = field(default_factory=list)
    uncertain_claim_ids: list[str] = field(default_factory=list)
    unmatched_claim_ids: list[str] = field(default_factory=list)
    insufficient_data_claim_ids: list[str] = field(default_factory=list)
    # Condition accounting -- three mutually exclusive categories, sum == total_conditions.
    linked_condition_ids: list[str] = field(default_factory=list)
    uncertain_condition_ids: list[str] = field(default_factory=list)
    unlinked_condition_ids: list[str] = field(default_factory=list)
    # Aggregate counts.
    total_claims: int = 0
    total_conditions: int = 0
    confirmed_link_count: int = 0
    possible_link_count: int = 0
    uncertain_link_count: int = 0
    # Keys: claim_ids in insufficient_data_claim_ids only.
    insufficient_data_reasons: dict[str, str] = field(default_factory=dict)


@dataclass
class LinkResult:
    links: list[ClaimConditionLink]
    summary: LinkerSummary


# ---------------------------------------------------------------------------
# Signal evaluation
# ---------------------------------------------------------------------------


def usable_batch_identifiers(batch_numbers: Sequence[str] | None) -> frozenset[str]:
    """Claim-side usable identifiers: non-empty after strip + lower.
    Internal characters (hyphens, spaces, dots) are preserved."""
    if not batch_numbers:
        return frozenset()
    return frozenset(
        b.strip().lower() for b in batch_numbers if b is not None and b.strip()
    )


def usable_batch_identifier(batch_number: str | None) -> str | None:
    if batch_number is None:
        return None
    stripped = batch_number.strip()
    return stripped.lower() if stripped else None


def evaluate_batch_signal(
    claim_batch_numbers: Sequence[str] | None,
    condition_batch_number: str | None,
) -> SignalOutcome:
    """Signal A.  ABSENT if either side has no usable identifier; STRONG
    on literal equality; otherwise DIVERGENT.  No weak outcome exists."""
    claim_usable = usable_batch_identifiers(claim_batch_numbers)
    cond_usable = usable_batch_identifier(condition_batch_number)
    if not claim_usable or cond_usable is None:
        return SignalOutcome.ABSENT
    if cond_usable in claim_usable:
        return SignalOutcome.STRONG_POSITIVE
    return SignalOutcome.DIVERGENT


def compare_component(component: str, condition_field: str | None) -> ComponentMatchNote:
    """Compare one claim component string against one condition field.

    Evaluation order (design v11 section 3):
      0. safeguard = contains_non_ascii(component) or contains_non_ascii(field)
      1. normalise both sides
      2. meaningful tokens (non-generic, non-connector); either empty -> ABSENT
      3. if not safeguard and evidentiary sequences equal -> STRONG_POSITIVE
      4. shared known material token among meaningful tokens -> WEAK_POSITIVE
      5. otherwise -> DIVERGENT
    """
    safeguard = contains_non_ascii(component) or contains_non_ascii(condition_field)

    claim_tokens = normalise_packaging(component)
    cond_tokens = normalise_packaging(condition_field)

    claim_meaningful = _meaningful(claim_tokens)
    cond_meaningful = _meaningful(cond_tokens)

    unclassified_claim = _unclassified(claim_meaningful)
    unclassified_cond = _unclassified(cond_meaningful)

    if not claim_meaningful or not cond_meaningful:
        return ComponentMatchNote(
            component_text=component,
            signal_outcome=SignalOutcome.ABSENT.value,
            shared_material_tokens=(),
            unclassified_tokens_claim=unclassified_claim,
            unclassified_tokens_condition=unclassified_cond,
            non_ascii_safeguard_applied=safeguard,
        )

    if not safeguard and _evidentiary(claim_tokens) == _evidentiary(cond_tokens):
        return ComponentMatchNote(
            component_text=component,
            signal_outcome=SignalOutcome.STRONG_POSITIVE.value,
            shared_material_tokens=(),
            unclassified_tokens_claim=unclassified_claim,
            unclassified_tokens_condition=unclassified_cond,
            non_ascii_safeguard_applied=safeguard,
        )

    shared_material = tuple(sorted(
        set(claim_meaningful) & set(cond_meaningful) & _KNOWN_MATERIAL_TOKENS
    ))
    if shared_material:
        outcome = SignalOutcome.WEAK_POSITIVE
    else:
        outcome = SignalOutcome.DIVERGENT

    return ComponentMatchNote(
        component_text=component,
        signal_outcome=outcome.value,
        shared_material_tokens=shared_material,
        unclassified_tokens_claim=unclassified_claim,
        unclassified_tokens_condition=unclassified_cond,
        non_ascii_safeguard_applied=safeguard,
    )


def evaluate_packaging_signal(
    components: Sequence[str] | None,
    condition_field: str | None,
) -> tuple[SignalOutcome, tuple[ComponentMatchNote, ...]]:
    """Signals B and C.  Each component is compared independently against
    the condition field; the signal outcome is the best per-component
    outcome (strong > weak > divergent > absent).  Component boundaries
    are never flattened.  Empty components -> ABSENT with no notes."""
    if not components:
        return SignalOutcome.ABSENT, ()
    notes = tuple(compare_component(c, condition_field) for c in components)
    best = max(
        (SignalOutcome(n.signal_outcome) for n in notes),
        key=lambda o: _OUTCOME_RANK[o],
    )
    return best, notes


def claim_has_linkable_batch(claim: S6Claim) -> bool:
    return bool(usable_batch_identifiers(claim.batch_numbers))


def claim_has_linkable_packaging(claim: S6Claim) -> bool:
    return any(_meaningful(normalise_packaging(c)) for c in claim.packaging_components)


# ---------------------------------------------------------------------------
# Classification (R1-R5)
# ---------------------------------------------------------------------------


def classify(
    a: SignalOutcome, b: SignalOutcome, c: SignalOutcome
) -> LinkClassification:
    """Apply R1-R5 in order; first match wins.  Covers all 64 combinations."""
    outcomes = (a, b, c)
    absent_count = sum(o is SignalOutcome.ABSENT for o in outcomes)
    strong_count = sum(o is SignalOutcome.STRONG_POSITIVE for o in outcomes)
    weak_count = sum(o is SignalOutcome.WEAK_POSITIVE for o in outcomes)
    divergent_count = sum(o is SignalOutcome.DIVERGENT for o in outcomes)

    # R1
    if absent_count == 3:
        return LinkClassification.INSUFFICIENT_DATA
    # R2
    if (
        a is SignalOutcome.STRONG_POSITIVE
        and (b is SignalOutcome.STRONG_POSITIVE or c is SignalOutcome.STRONG_POSITIVE)
        and divergent_count == 0
    ):
        return LinkClassification.CONFIRMED_MATCH
    # R3
    if divergent_count == 0 and strong_count >= 1:
        return LinkClassification.POSSIBLE_MATCH
    # R4
    if divergent_count == 3 and strong_count == 0 and weak_count == 0:
        return LinkClassification.NO_MATCH
    # R5
    return LinkClassification.UNCERTAIN_COMPARISON


_EMITTED: frozenset[LinkClassification] = frozenset({
    LinkClassification.CONFIRMED_MATCH,
    LinkClassification.POSSIBLE_MATCH,
    LinkClassification.UNCERTAIN_COMPARISON,
})


# ---------------------------------------------------------------------------
# Pair evaluation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _PairOutcome:
    """Internal full result for one (claim, condition) pair, including
    pairs that are not emitted as links."""

    classification: LinkClassification
    link: ClaimConditionLink


def _build_notes(
    classification: LinkClassification,
    outcomes: dict[str, SignalOutcome],
    notes_b: tuple[ComponentMatchNote, ...],
    notes_c: tuple[ComponentMatchNote, ...],
    claim: S6Claim,
    condition: S7StabilityCondition,
) -> str:
    parts: list[str] = [
        f"classification={classification.value}",
        "signals: " + ", ".join(f"{s}={outcomes[s].value}" for s in ALL_SIGNALS),
    ]
    connector_seen: set[str] = set()
    for comp in claim.packaging_components:
        connector_seen.update(_connectors(normalise_packaging(comp)))
    for fld in (condition.packaging_reference, condition.container_reference):
        connector_seen.update(_connectors(normalise_packaging(fld)))
    if connector_seen:
        parts.append("connector tokens ignored: " + ", ".join(sorted(connector_seen)))
    for label, notes in (("B", notes_b), ("C", notes_c)):
        for idx, n in enumerate(notes):
            if n.non_ascii_safeguard_applied:
                parts.append(f"non-ASCII safeguard applied to signal {label} component {idx}")
    if classification in (LinkClassification.CONFIRMED_MATCH, LinkClassification.POSSIBLE_MATCH):
        if (
            outcomes[SIGNAL_BATCH] is SignalOutcome.STRONG_POSITIVE
            and outcomes[SIGNAL_PACKAGING] is SignalOutcome.ABSENT
            and outcomes[SIGNAL_CONTAINER] is SignalOutcome.ABSENT
        ):
            parts.append(
                "Batch identifier match only. Packaging fields were absent. "
                "No packaging comparison was possible; the batch link does not "
                "confirm that the packaging described in S.7 matches S.6."
            )
        else:
            parts.append(
                "One or more claim packaging components matched the condition "
                "description. Matching one component does not confirm that "
                "complete packaging systems are identical. Downstream evaluation "
                "must assess all components."
            )
    parts.append(
        "This link records lexical relatedness evidence only; it is not a "
        "regulatory verdict and asserts no contradiction."
    )
    return " | ".join(parts)


def evaluate_pair(claim: S6Claim, condition: S7StabilityCondition) -> _PairOutcome:
    a = evaluate_batch_signal(claim.batch_numbers, condition.batch_number)
    b, notes_b = evaluate_packaging_signal(
        claim.packaging_components, condition.packaging_reference
    )
    c, notes_c = evaluate_packaging_signal(
        claim.packaging_components, condition.container_reference
    )
    outcomes = {SIGNAL_BATCH: a, SIGNAL_PACKAGING: b, SIGNAL_CONTAINER: c}
    classification = classify(a, b, c)

    def _with(outcome: SignalOutcome) -> tuple[str, ...]:
        return tuple(s for s in ALL_SIGNALS if outcomes[s] is outcome)

    link = ClaimConditionLink(
        claim_id=claim.claim_id,
        condition_id=condition.condition_id,
        classification=classification,
        strong_signals=_with(SignalOutcome.STRONG_POSITIVE),
        weak_signals=_with(SignalOutcome.WEAK_POSITIVE),
        divergent_signals=_with(SignalOutcome.DIVERGENT),
        absent_signals=_with(SignalOutcome.ABSENT),
        claim_source_ref=claim.source_ref.model_copy(deep=True),
        condition_source_ref=condition.source_ref.model_copy(deep=True),
        component_notes_b=notes_b,
        component_notes_c=notes_c,
        notes=_build_notes(classification, outcomes, notes_b, notes_c, claim, condition),
    )
    return _PairOutcome(classification=classification, link=link)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

# Claim-category precedence (best outcome across all conditions wins).
_CLAIM_PRECEDENCE: tuple[LinkClassification, ...] = (
    LinkClassification.CONFIRMED_MATCH,
    LinkClassification.POSSIBLE_MATCH,
    LinkClassification.UNCERTAIN_COMPARISON,
    LinkClassification.NO_MATCH,
    LinkClassification.INSUFFICIENT_DATA,
)


def link_stability_conditions(
    claims: Sequence[S6Claim],
    conditions: Sequence[S7StabilityCondition],
) -> LinkResult:
    """Compare every claim against every condition and return emitted
    links (CONFIRMED / POSSIBLE / UNCERTAIN only) plus full accounting.

    Deterministic: identical inputs yield identical output; emitted links
    are sorted by (claim_id, condition_id).
    """
    summary = LinkerSummary(total_claims=len(claims), total_conditions=len(conditions))
    emitted: list[ClaimConditionLink] = []

    # Condition-level bookkeeping.
    cond_best: dict[str, LinkClassification] = {}

    for claim in claims:
        if not conditions:
            summary.insufficient_data_claim_ids.append(claim.claim_id)
            summary.insufficient_data_reasons[claim.claim_id] = REASON_NO_CONDITIONS
            continue

        pair_classes: list[LinkClassification] = []
        for condition in conditions:
            pair = evaluate_pair(claim, condition)
            pair_classes.append(pair.classification)
            if pair.classification in _EMITTED:
                emitted.append(pair.link)
            prev = cond_best.get(condition.condition_id)
            if prev is None or _CLAIM_PRECEDENCE.index(pair.classification) < _CLAIM_PRECEDENCE.index(prev):
                cond_best[condition.condition_id] = pair.classification

        best = min(pair_classes, key=_CLAIM_PRECEDENCE.index)
        if best is LinkClassification.CONFIRMED_MATCH:
            summary.confirmed_claim_ids.append(claim.claim_id)
        elif best is LinkClassification.POSSIBLE_MATCH:
            summary.possible_claim_ids.append(claim.claim_id)
        elif best is LinkClassification.UNCERTAIN_COMPARISON:
            summary.uncertain_claim_ids.append(claim.claim_id)
        elif best is LinkClassification.NO_MATCH:
            summary.unmatched_claim_ids.append(claim.claim_id)
        else:
            summary.insufficient_data_claim_ids.append(claim.claim_id)
            if not claim_has_linkable_batch(claim) and not claim_has_linkable_packaging(claim):
                summary.insufficient_data_reasons[claim.claim_id] = REASON_NO_LINKABLE_FIELDS
            else:
                summary.insufficient_data_reasons[claim.claim_id] = REASON_ALL_PAIRS_INSUFFICIENT

    for condition in conditions:
        best_c = cond_best.get(condition.condition_id)
        if best_c in (LinkClassification.CONFIRMED_MATCH, LinkClassification.POSSIBLE_MATCH):
            summary.linked_condition_ids.append(condition.condition_id)
        elif best_c is LinkClassification.UNCERTAIN_COMPARISON:
            summary.uncertain_condition_ids.append(condition.condition_id)
        else:
            summary.unlinked_condition_ids.append(condition.condition_id)

    emitted.sort(key=lambda l: (l.claim_id, l.condition_id))
    summary.confirmed_link_count = sum(
        l.classification is LinkClassification.CONFIRMED_MATCH for l in emitted
    )
    summary.possible_link_count = sum(
        l.classification is LinkClassification.POSSIBLE_MATCH for l in emitted
    )
    summary.uncertain_link_count = sum(
        l.classification is LinkClassification.UNCERTAIN_COMPARISON for l in emitted
    )
    return LinkResult(links=emitted, summary=summary)
