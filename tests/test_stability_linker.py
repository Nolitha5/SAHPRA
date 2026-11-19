"""
Tests for src/container_closure/stability_linker.py -- Phase 4b (design v11).

Group map (design v11 / v9 / v8 numbering):
  31  normalisation contract (complete-function) and ASCII predicates
  32  Signal A batch identifiers (incl. blank / whitespace entries)
  33  packaging evaluation precedence and connector handling
  34  linkable fields and insufficient-data reason precedence
  35  non-ASCII fragmentation and safeguard
  20  all 64 signal combinations (R1-R5 distribution 1/5/14/1/43)
  1-19, 21-30  classification scenarios, best-of-N, accounting,
               source refs, determinism, immutability, no conflict class
All data is synthetic.
"""
from __future__ import annotations

import dataclasses
from itertools import product

import pytest

from container_closure.stability_linker import (
    ALL_SIGNALS,
    REASON_ALL_PAIRS_INSUFFICIENT,
    REASON_NO_CONDITIONS,
    REASON_NO_LINKABLE_FIELDS,
    SIGNAL_BATCH,
    SIGNAL_CONTAINER,
    SIGNAL_PACKAGING,
    ClaimConditionLink,
    ComponentMatchNote,
    LinkClassification,
    LinkResult,
    LinkerSummary,
    SignalOutcome,
    _CONNECTOR_TOKENS,
    _GENERIC_PACKAGING_TOKENS,
    _KNOWN_MATERIAL_TOKENS,
    _is_ascii_digit,
    _is_ascii_lower,
    classify,
    compare_component,
    contains_non_ascii,
    evaluate_batch_signal,
    evaluate_packaging_signal,
    link_stability_conditions,
    normalise_packaging,
)
from shared.models import S6Claim, S7StabilityCondition, SourceReference
from tests.fixtures.s6_fixtures import (
    fixture_source_ref,
    fixture_stability_source_ref,
)

S = SignalOutcome.STRONG_POSITIVE
W = SignalOutcome.WEAK_POSITIVE
D = SignalOutcome.DIVERGENT
X = SignalOutcome.ABSENT

CONF = LinkClassification.CONFIRMED_MATCH
POSS = LinkClassification.POSSIBLE_MATCH
UNC = LinkClassification.UNCERTAIN_COMPARISON
NOM = LinkClassification.NO_MATCH
INS = LinkClassification.INSUFFICIENT_DATA


# ---------------------------------------------------------------------------
# Synthetic builders
# ---------------------------------------------------------------------------


def claim(
    claim_id: str = "c-1",
    batch: list[str] | None = None,
    comps: list[str] | None = None,
    source_id: str = "doc-c",
) -> S6Claim:
    return S6Claim(
        claim_id=claim_id,
        text="[SYNTHETIC] claim text",
        source_ref=fixture_source_ref(source_id=source_id),
        batch_numbers=batch if batch is not None else [],
        packaging_components=comps if comps is not None else [],
    )


def cond(
    condition_id: str = "s-1",
    batch: str | None = None,
    pkg: str | None = None,
    cont: str | None = None,
    source_id: str = "stab-c",
) -> S7StabilityCondition:
    return S7StabilityCondition(
        condition_id=condition_id,
        storage_condition="[SYNTHETIC] 25C/60%RH",
        batch_number=batch,
        packaging_reference=pkg,
        container_reference=cont,
        source_ref=fixture_stability_source_ref(source_id=source_id),
    )


def outcome(comp: str, fld: str | None) -> str:
    return compare_component(comp, fld).signal_outcome


def single_link(result: LinkResult) -> ClaimConditionLink:
    assert len(result.links) == 1
    return result.links[0]


def assert_claim_invariant(summary: LinkerSummary) -> None:
    assert (
        len(summary.confirmed_claim_ids)
        + len(summary.possible_claim_ids)
        + len(summary.uncertain_claim_ids)
        + len(summary.unmatched_claim_ids)
        + len(summary.insufficient_data_claim_ids)
        == summary.total_claims
    )
    assert (
        len(summary.linked_condition_ids)
        + len(summary.uncertain_condition_ids)
        + len(summary.unlinked_condition_ids)
        == summary.total_conditions
    )
    assert set(summary.insufficient_data_reasons) == set(summary.insufficient_data_claim_ids)


# ---------------------------------------------------------------------------
# Group 31 -- normalisation contract
# ---------------------------------------------------------------------------


class TestGroup31Normalisation:
    @pytest.mark.parametrize(
        "text, expected",
        [
            ("10.5 mL", ["10.5", "ml"]),
            ("10-20 mm", ["10-20", "mm"]),
            ("v2.0 vial", ["v2.0", "vial"]),
            ("vial.stopper", ["vial", "stopper"]),
            ("10.5mL", ["10.5ml"]),
            ("10-20-30", ["10-20-30"]),
            ("1.-2", ["1", "2"]),
            ("-10", ["10"]),
            ("10-", ["10"]),
            (".5", ["5"]),
            ("5.", ["5"]),
            ("-", []),
            (".", []),
            ("HDPE/PET", ["hdpe", "pet"]),
            ("HDPE/PET laminate", ["hdpe", "pet", "laminate"]),
            ("10 mL", ["10", "ml"]),
            ("10mL", ["10ml"]),
            ("bromobutyl-rubber", ["bromobutyl", "rubber"]),
            ("HDPE-cap", ["hdpe", "cap"]),
            ("BN-001", ["bn", "001"]),
            ("stérile", ["st", "rile"]),
            ("flacon 10 mL stérile", ["flacon", "10", "ml", "st", "rile"]),
            ("Glasflasche ß", ["glasflasche"]),
            ("флакон", []),
            ("10 µL", ["10", "l"]),
            ("5°C", ["5", "c"]),
            ("Ⅻ vial", ["vial"]),
            ("glass  vial", ["glass", "vial"]),
            ("glass\tvial", ["glass", "vial"]),
            ("glass\nvial", ["glass", "vial"]),
            ("glass\r\nvial", ["glass", "vial"]),
            ("glass vial", ["glass", "vial"]),
            ("glass glass vial", ["glass", "glass", "vial"]),
            ("manufacturer's vial", ["manufacturer", "s", "vial"]),
            ("vial (2R)", ["vial", "2r"]),
            ("Glass_Vial", ["glass", "vial"]),
            ("with", ["with"]),
            ("", []),
            ("   ", []),
            (None, []),
        ],
    )
    def test_complete_function(self, text, expected):
        assert normalise_packaging(text) == expected

    @pytest.mark.parametrize("c", ["a", "m", "z"])
    def test_ascii_lower_true(self, c):
        assert _is_ascii_lower(c)

    @pytest.mark.parametrize("c", ["A", "é", "ß", "0", " ", "б"])
    def test_ascii_lower_false(self, c):
        assert not _is_ascii_lower(c)

    @pytest.mark.parametrize("c", ["0", "5", "9"])
    def test_ascii_digit_true(self, c):
        assert _is_ascii_digit(c)

    @pytest.mark.parametrize("c", ["²", "٣", "Ⅻ", "a", "-"])
    def test_ascii_digit_false(self, c):
        # str.isdigit() would return True for superscript 2 and Arabic-Indic 3.
        assert not _is_ascii_digit(c)

    def test_neighbour_check_never_wraps(self):
        # If negative indexing were used, "-" at index 0 would see "1" at s[-1].
        assert normalise_packaging("-1") == ["1"]
        assert normalise_packaging("1-") == ["1"]
        assert normalise_packaging(".1") == ["1"]
        assert normalise_packaging("1.") == ["1"]

    def test_vocabularies_disjoint(self):
        assert not (_GENERIC_PACKAGING_TOKENS & _CONNECTOR_TOKENS)
        assert not (_GENERIC_PACKAGING_TOKENS & _KNOWN_MATERIAL_TOKENS)
        assert not (_CONNECTOR_TOKENS & _KNOWN_MATERIAL_TOKENS)

    @pytest.mark.parametrize("text, expected", [
        ("glass vial", False), ("", False), (None, False),
        ("stérile", True), ("glass vial", True), ("5°C", True),
        ("ф", True),
    ])
    def test_contains_non_ascii(self, text, expected):
        assert contains_non_ascii(text) is expected


# ---------------------------------------------------------------------------
# Group 32 -- Signal A
# ---------------------------------------------------------------------------


class TestGroup32BatchSignal:
    @pytest.mark.parametrize(
        "claim_batches, cond_batch, expected",
        [
            (["BN-001"], "BN-001", S),
            (["BN-001"], "bn-001", S),
            (["BN-001"], "  BN-001 ", S),
            (["BN-001"], "BN001", D),
            (["BN-001"], "BN 001", D),
            (["BN-001"], "BN_001", D),
            ([], "BN-001", X),
            (["BN-001"], None, X),
            (["BN-001", "BN-002"], "BN-002", S),
            ([""], "BN-001", X),
            (["   "], "BN-001", X),
            (["", "  ", "BN-001"], "BN-001", S),
            (["BN-001"], "", X),
            (["BN-001"], "   ", X),
            (["  "], "  ", X),
            (["LOT-É1"], "lot-é1", S),   # literal equality after lower()
            (["LOT-É1"], "LOT-E1", D),
        ],
    )
    def test_batch(self, claim_batches, cond_batch, expected):
        assert evaluate_batch_signal(claim_batches, cond_batch) is expected


# ---------------------------------------------------------------------------
# Group 33 -- precedence and connector handling
# ---------------------------------------------------------------------------


class TestGroup33Precedence:
    @pytest.mark.parametrize(
        "comp, fld, expected",
        [
            ("bottle", "bottle", "absent"),
            ("vial", "vial", "absent"),
            ("bottle cap", "cap bottle", "absent"),
            ("HDPE bottle", "HDPE bottle", "strong_positive"),
            ("glass vial", "glass vial", "strong_positive"),
            ("glass vial", "glass bottle", "weak_positive"),
            ("bottle with cap", "glass bottle", "absent"),
            ("bottle with cap", "bottle with cap", "absent"),
            ("aluminium cap", "aluminum cap", "divergent"),
            ("PTFE liner", "PTFE liner", "strong_positive"),
            ("laminate pouch", "laminate pouch", "strong_positive"),
            ("glass vial with cap", "glass vial cap", "strong_positive"),
            ("with and of", "with and of", "absent"),
            ("PTFE liner", "laminate liner", "divergent"),
            ("glass vial with HDPE cap", "glass vial", "weak_positive"),
            ("glass glass vial", "glass vial", "weak_positive"),      # duplicates preserved
            ("10 mL glass vial", "10mL glass vial", "weak_positive"),  # numeric spacing
            ("glass vial", None, "absent"),
            ("", "glass vial", "absent"),
        ],
    )
    def test_outcome(self, comp, fld, expected):
        assert outcome(comp, fld) == expected

    def test_note_contents_strong(self):
        n = compare_component("HDPE bottle", "HDPE bottle")
        assert n.shared_material_tokens == ()
        assert n.unclassified_tokens_claim == ()
        assert n.non_ascii_safeguard_applied is False
        assert n.component_text == "HDPE bottle"

    def test_note_contents_weak(self):
        n = compare_component("glass vial", "glass bottle")
        assert n.shared_material_tokens == ("glass",)

    def test_note_unclassified_technical(self):
        n = compare_component("PTFE liner", "PTFE liner")
        assert n.unclassified_tokens_claim == ("ptfe",)
        assert n.unclassified_tokens_condition == ("ptfe",)

    def test_connector_not_recorded_as_unclassified(self):
        n = compare_component("glass vial with HDPE cap", "glass vial")
        assert n.unclassified_tokens_claim == ()
        assert n.shared_material_tokens == ("glass",)

    def test_connector_listed_in_link_notes(self):
        r = link_stability_conditions(
            [claim(comps=["glass vial with HDPE cap"])], [cond(pkg="glass vial")]
        )
        link = single_link(r)
        assert "connector tokens ignored: with" in link.notes

    def test_generic_only_pair_is_insufficient(self):
        r = link_stability_conditions([claim(comps=["bottle"])], [cond(pkg="bottle")])
        assert r.links == []
        assert r.summary.insufficient_data_reasons == {"c-1": REASON_NO_LINKABLE_FIELDS}

    def test_identical_unclassified_pair_is_possible(self):
        r = link_stability_conditions([claim(comps=["PTFE liner"])], [cond(pkg="PTFE liner")])
        assert single_link(r).classification is POSS
        assert r.summary.possible_claim_ids == ["c-1"]

    def test_divergent_unclassified_pair_is_uncertain(self):
        r = link_stability_conditions([claim(comps=["PTFE liner"])], [cond(pkg="laminate liner")])
        assert single_link(r).classification is UNC


# ---------------------------------------------------------------------------
# Group 34 -- linkable fields and reason precedence
# ---------------------------------------------------------------------------


class TestGroup34Reasons:
    def test_no_conditions_wins_over_no_fields(self):
        r = link_stability_conditions([claim(batch=[], comps=["bottle"])], [])
        assert r.summary.insufficient_data_reasons == {"c-1": REASON_NO_CONDITIONS}
        assert r.summary.total_conditions == 0
        assert r.links == []
        assert_claim_invariant(r.summary)

    def test_blank_batch_and_no_components(self):
        r = link_stability_conditions([claim(batch=["  "], comps=[])], [cond(batch="BN-1", pkg="glass vial")])
        assert r.summary.insufficient_data_reasons == {"c-1": REASON_NO_LINKABLE_FIELDS}

    def test_generic_only_component(self):
        r = link_stability_conditions([claim(comps=["bottle"])], [cond(batch="BN-1", pkg="glass vial")])
        assert r.summary.insufficient_data_reasons == {"c-1": REASON_NO_LINKABLE_FIELDS}

    def test_generic_and_connector_component(self):
        r = link_stability_conditions([claim(comps=["bottle with cap"])], [cond(batch="BN-1", pkg="glass vial")])
        assert r.summary.insufficient_data_reasons == {"c-1": REASON_NO_LINKABLE_FIELDS}

    def test_all_pairs_insufficient_batch_only_claim(self):
        r = link_stability_conditions([claim(batch=["BN-001"])], [cond()])
        assert r.summary.insufficient_data_reasons == {"c-1": REASON_ALL_PAIRS_INSUFFICIENT}

    def test_all_pairs_insufficient_packaging_only_claim(self):
        r = link_stability_conditions([claim(comps=["glass vial"])], [cond(batch="BN-001")])
        assert r.summary.insufficient_data_reasons == {"c-1": REASON_ALL_PAIRS_INSUFFICIENT}

    def test_all_pairs_insufficient_technical_component(self):
        r = link_stability_conditions([claim(comps=["PTFE liner"])], [cond(batch="BN-001")])
        assert r.summary.insufficient_data_reasons == {"c-1": REASON_ALL_PAIRS_INSUFFICIENT}

    def test_reasons_only_for_insufficient_claims(self):
        r = link_stability_conditions(
            [claim("c-a", batch=["BN-1"]), claim("c-b", comps=["glass vial"])],
            [cond(batch="BN-1")],
        )
        assert r.summary.possible_claim_ids == ["c-a"]
        assert r.summary.insufficient_data_claim_ids == ["c-b"]
        assert set(r.summary.insufficient_data_reasons) == {"c-b"}


# ---------------------------------------------------------------------------
# Group 35 -- non-ASCII fragmentation and safeguard
# ---------------------------------------------------------------------------


class TestGroup35NonAscii:
    @pytest.mark.parametrize(
        "comp, fld, expected, flag",
        [
            ("stérile", "sterile", "divergent", True),
            ("stérile vial", "sterile vial", "divergent", True),
            ("flacon", "flacon", "strong_positive", False),
            ("flacon vial", "flacon vial", "strong_positive", False),
            ("stérile", "stérile", "divergent", True),
            ("stérile glass vial", "sterile glass vial", "weak_positive", True),
            ("é", "sterile", "absent", True),
            ("флакон vial", "vial", "absent", True),
            ("stérile", "st rile", "divergent", True),
            ("ppé bottle", "pp bottle", "weak_positive", True),
            ("ppé bottle", "pp vial", "weak_positive", True),
            ("capé", "cap", "absent", True),
            ("glass vial", "glass vial", "strong_positive", False),
            ("glass vial", "glass viàl", "weak_positive", True),         # condition-side trigger
            ("glass vial", "glass vial", "weak_positive", True),         # U+00A0
            ("stérile", "stérile", "divergent", True),            # NFC vs NFD
        ],
    )
    def test_outcome_and_flag(self, comp, fld, expected, flag):
        n = compare_component(comp, fld)
        assert n.signal_outcome == expected
        assert n.non_ascii_safeguard_applied is flag

    def test_35a_note_details(self):
        n = compare_component("stérile", "sterile")
        assert n.unclassified_tokens_claim == ("rile", "st")
        assert n.unclassified_tokens_condition == ("sterile",)
        assert n.shared_material_tokens == ()

    def test_35j_shared_material_recorded(self):
        n = compare_component("ppé bottle", "pp bottle")
        assert n.shared_material_tokens == ("pp",)

    def test_nfc_nfd_tokens(self):
        assert normalise_packaging("stérile") == ["st", "rile"]
        assert normalise_packaging("stérile") == ["ste", "rile"]

    def test_35m_follow_through_uncertain(self):
        r = link_stability_conditions([claim(comps=["stérile"])], [cond(pkg="sterile")])
        link = single_link(r)
        assert link.classification is UNC
        assert r.summary.uncertain_claim_ids == ["c-1"]
        assert r.summary.uncertain_condition_ids == ["s-1"]
        assert "non-ASCII safeguard applied to signal B component 0" in link.notes

    def test_35n_follow_through_possible(self):
        r = link_stability_conditions([claim(comps=["flacon"])], [cond(pkg="flacon")])
        assert single_link(r).classification is POSS
        assert r.summary.possible_claim_ids == ["c-1"]

    def test_35q_best_of_n_with_flagged_component(self):
        sig, notes = evaluate_packaging_signal(["stérile vial", "glass vial"], "glass vial")
        assert sig is S
        assert len(notes) == 2
        assert notes[0].signal_outcome == "divergent" and notes[0].non_ascii_safeguard_applied
        assert notes[1].signal_outcome == "strong_positive" and not notes[1].non_ascii_safeguard_applied

    def test_35t_safeguard_blocks_strong_for_any_accented_variant(self):
        base_strings = ["glass vial", "HDPE bottle", "PTFE liner", "borosilicate glass vial 2R",
                        "bromobutyl stopper 20mm", "laminate pouch", "PET film"]
        for s in base_strings:
            for i, ch in enumerate(s):
                if "a" <= ch.lower() <= "z":
                    accented = s[:i] + "é" + s[i + 1:]
                    for a, b in ((accented, s), (s, accented), (accented, accented)):
                        n = compare_component(a, b)
                        assert n.non_ascii_safeguard_applied is True
                        assert n.signal_outcome != "strong_positive", (a, b)

    def test_safeguard_is_pairwise_signal_b_vs_c_independent(self):
        c = cond(pkg="glass viàl", cont="glass vial")
        r = link_stability_conditions([claim(comps=["glass vial"])], [c])
        link = single_link(r)
        assert link.weak_signals == (SIGNAL_PACKAGING,)
        assert link.strong_signals == (SIGNAL_CONTAINER,)
        assert link.component_notes_b[0].non_ascii_safeguard_applied is True
        assert link.component_notes_c[0].non_ascii_safeguard_applied is False


# ---------------------------------------------------------------------------
# Group 20 -- all 64 combinations
# ---------------------------------------------------------------------------


def _expected(a, b, c):
    outs = (a, b, c)
    if all(o is X for o in outs):
        return INS
    if a is S and (b is S or c is S) and D not in outs:
        return CONF
    if D not in outs and S in outs:
        return POSS
    if all(o is D for o in outs):
        return NOM
    return UNC


class TestGroup20AllCombinations:
    @pytest.mark.parametrize("a, b, c", list(product([S, W, D, X], repeat=3)))
    def test_each_combination(self, a, b, c):
        assert classify(a, b, c) is _expected(a, b, c)

    def test_distribution(self):
        counts = {k: 0 for k in LinkClassification}
        for a, b, c in product([S, W, D, X], repeat=3):
            counts[classify(a, b, c)] += 1
        assert counts[INS] == 1
        assert counts[CONF] == 5
        assert counts[POSS] == 14
        assert counts[NOM] == 1
        assert counts[UNC] == 43
        assert sum(counts.values()) == 64

    def test_b_plus_c_without_a_is_possible(self):
        assert classify(X, S, S) is POSS

    def test_two_weak_without_batch_is_uncertain(self):
        assert classify(X, W, W) is UNC

    def test_no_conflict_classification_exists(self):
        assert "POTENTIAL_CONFLICT" not in {m.value for m in LinkClassification}
        assert len(LinkClassification) == 5


# ---------------------------------------------------------------------------
# Scenario groups (1-19)
# ---------------------------------------------------------------------------


class TestScenarios:
    def test_g1_exact_batch_and_packaging_confirmed(self):
        r = link_stability_conditions(
            [claim(batch=["BN-001"], comps=["bromobutyl stopper 20mm"])],
            [cond(batch="BN-001", pkg="bromobutyl stopper 20mm")],
        )
        link = single_link(r)
        assert link.classification is CONF
        assert set(link.strong_signals) == {SIGNAL_BATCH, SIGNAL_PACKAGING}
        assert link.absent_signals == (SIGNAL_CONTAINER,)
        assert link.component_notes_b[0].signal_outcome == "strong_positive"
        assert "Matching one component does not confirm" in link.notes
        assert r.summary.confirmed_claim_ids == ["c-1"]
        assert r.summary.linked_condition_ids == ["s-1"]
        assert r.summary.confirmed_link_count == 1

    def test_g2_shared_material_different_description(self):
        r = link_stability_conditions([claim(comps=["glass vial"])], [cond(pkg="glass bottle")])
        link = single_link(r)
        assert link.classification is UNC
        assert link.weak_signals == (SIGNAL_PACKAGING,)

    def test_g5_borosilicate_is_material(self):
        assert "borosilicate" in _KNOWN_MATERIAL_TOKENS
        assert outcome("borosilicate glass vial", "borosilicate glass ampoule") == "weak_positive"

    def test_g6_identical_borosilicate_possible_not_confirmed(self):
        r = link_stability_conditions(
            [claim(comps=["borosilicate glass vial 2R"])], [cond(pkg="borosilicate glass vial 2R")]
        )
        assert single_link(r).classification is POSS

    @pytest.mark.parametrize("text", ["HDPE bottle", "PVC tubing", "PET tray", "PET film"])
    def test_g7_9_identical_material_descriptions_possible(self, text):
        r = link_stability_conditions([claim(comps=[text])], [cond(pkg=text)])
        assert single_link(r).classification is POSS

    def test_g10_glass_vs_hdpe_cap_no_conflict(self):
        r = link_stability_conditions(
            [claim(batch=["BN-001"], comps=["glass vial with HDPE cap"])],
            [cond(batch="BN-001", pkg="glass vial")],
        )
        link = single_link(r)
        assert link.classification is POSS      # A strong, B weak, no divergent -> R3
        assert link.component_notes_b[0].unclassified_tokens_claim == ()

    def test_g11_best_of_n_preserves_component_boundaries(self):
        r = link_stability_conditions(
            [claim(comps=["glass vial 2R", "bromobutyl stopper", "aluminium cap"])],
            [cond(pkg="bromobutyl stopper")],
        )
        link = single_link(r)
        assert link.classification is POSS
        assert link.strong_signals == (SIGNAL_PACKAGING,)
        assert [n.signal_outcome for n in link.component_notes_b] == [
            "divergent", "strong_positive", "divergent"
        ]
        assert [n.component_text for n in link.component_notes_b] == [
            "glass vial 2R", "bromobutyl stopper", "aluminium cap"
        ]
        # No cross-component pooling: a condition describing both would not match.
        assert outcome("glass vial 2R", "glass bromobutyl stopper") == "weak_positive"

    def test_g14_generic_form_words(self):
        assert outcome("silicone membrane", "rubber membrane") == "divergent"
        assert outcome("PVC tubing", "HDPE tubing") == "divergent"
        assert outcome("PET film", "PET film") == "strong_positive"

    def test_g15_laminate_unclassified(self):
        assert "laminate" not in _GENERIC_PACKAGING_TOKENS
        assert "laminate" not in _KNOWN_MATERIAL_TOKENS
        assert outcome("aluminium foil laminate", "aluminium foil") == "weak_positive"
        assert outcome("aluminium foil laminate", "aluminium foil laminate") == "strong_positive"

    def test_g16_b_plus_c_without_a(self):
        r = link_stability_conditions(
            [claim(comps=["borosilicate glass vial 2R"])],
            [cond(pkg="borosilicate glass vial 2R", cont="borosilicate glass vial 2R")],
        )
        link = single_link(r)
        assert link.classification is POSS
        assert set(link.strong_signals) == {SIGNAL_PACKAGING, SIGNAL_CONTAINER}

    def test_g17_correlated_weak_b_c_uncertain(self):
        r = link_stability_conditions(
            [claim(comps=["glass stopper"])], [cond(pkg="glass vial", cont="glass bottle")]
        )
        link = single_link(r)
        assert link.classification is UNC
        assert set(link.weak_signals) == {SIGNAL_PACKAGING, SIGNAL_CONTAINER}

    def test_g18_batch_only_possible_with_limitation_note(self):
        r = link_stability_conditions([claim(batch=["BN-001"])], [cond(batch="BN-001")])
        link = single_link(r)
        assert link.classification is POSS
        assert link.strong_signals == (SIGNAL_BATCH,)
        assert set(link.absent_signals) == {SIGNAL_PACKAGING, SIGNAL_CONTAINER}
        assert link.component_notes_b == () and link.component_notes_c == ()
        assert "Batch identifier match only" in link.notes

    def test_g19_divergent_vs_absent(self):
        d = link_stability_conditions(
            [claim(batch=["BN-001"], comps=["bromobutyl stopper"])],
            [cond(batch="BN-999", pkg="aluminium crimp cap")],
        )
        link = single_link(d)
        assert link.classification is UNC
        assert set(link.divergent_signals) == {SIGNAL_BATCH, SIGNAL_PACKAGING}
        assert link.absent_signals == (SIGNAL_CONTAINER,)
        a = link_stability_conditions([claim()], [cond(batch="BN-999", pkg="aluminium crimp cap")])
        assert a.links == []
        assert a.summary.insufficient_data_claim_ids == ["c-1"]

    def test_no_match_all_divergent(self):
        r = link_stability_conditions(
            [claim(batch=["BN-001"], comps=["bromobutyl stopper"])],
            [cond(batch="BN-002", pkg="aluminium cap", cont="PTFE liner")],
        )
        assert r.links == []
        assert r.summary.unmatched_claim_ids == ["c-1"]
        assert r.summary.unlinked_condition_ids == ["s-1"]

    def test_g27_glass_vs_hdpe_with_batch_is_uncertain_not_conflict(self):
        r = link_stability_conditions(
            [claim(batch=["BN-001"], comps=["glass vial"])], [cond(batch="BN-001", pkg="HDPE bottle")]
        )
        link = single_link(r)
        assert link.classification is UNC
        assert link.strong_signals == (SIGNAL_BATCH,)
        assert link.divergent_signals == (SIGNAL_PACKAGING,)
        assert "contradiction" not in link.classification.value.lower()


# ---------------------------------------------------------------------------
# Accounting (21-24), source refs (25), determinism (26), immutability (28),
# completeness (29), notes (30)
# ---------------------------------------------------------------------------


def _five_category_fixture():
    claims = [
        claim("c-conf", batch=["BN-1"], comps=["glass vial"]),
        claim("c-poss", batch=["BN-2"]),
        claim("c-unc", comps=["PTFE liner"]),
        claim("c-nom", batch=["BN-X"], comps=["bromobutyl stopper"]),
        claim("c-ins", batch=["  "], comps=["bottle"]),
    ]
    conditions = [
        cond("s-1", batch="BN-1", pkg="glass vial"),
        cond("s-2", batch="BN-2"),
        cond("s-3", pkg="laminate liner"),
        cond("s-4", batch="BN-Y", pkg="aluminium cap", cont="PET film"),
        cond("s-5"),
    ]
    return claims, conditions


class TestAccounting:
    def test_g21_five_claim_categories(self):
        claims, conditions = _five_category_fixture()
        r = link_stability_conditions(claims, conditions)
        s = r.summary
        assert s.confirmed_claim_ids == ["c-conf"]
        assert "c-poss" in s.possible_claim_ids
        assert s.unmatched_claim_ids == []
        # c-nom: vs s-4 all three divergent -> NO_MATCH; vs s-3 (B divergent, others absent) -> UNCERTAIN
        assert "c-nom" in s.uncertain_claim_ids
        assert s.insufficient_data_claim_ids == ["c-ins"]
        assert s.insufficient_data_reasons == {"c-ins": REASON_NO_LINKABLE_FIELDS}
        assert_claim_invariant(s)

    def test_g22_three_condition_categories(self):
        r = link_stability_conditions(
            [claim("c-1", batch=["BN-1"], comps=["glass vial"]), claim("c-2", comps=["PTFE liner"])],
            [cond("s-link", batch="BN-1", pkg="glass vial"), cond("s-unc", pkg="laminate liner"), cond("s-none")],
        )
        s = r.summary
        assert s.linked_condition_ids == ["s-link"]
        assert s.uncertain_condition_ids == ["s-unc"]
        assert s.unlinked_condition_ids == ["s-none"]
        assert_claim_invariant(s)

    def test_pure_no_match_claim(self):
        r = link_stability_conditions(
            [claim("c-nom", batch=["BN-X"], comps=["bromobutyl stopper"])],
            [cond("s-4", batch="BN-Y", pkg="aluminium cap", cont="PET film")],
        )
        assert r.summary.unmatched_claim_ids == ["c-nom"]
        assert r.summary.unlinked_condition_ids == ["s-4"]
        assert_claim_invariant(r.summary)

    def test_mixed_no_match_and_insufficient(self):
        r = link_stability_conditions(
            [claim("c-1", batch=["BN-X"], comps=["bromobutyl stopper"])],
            [cond("s-4", batch="BN-Y", pkg="aluminium cap", cont="PET film"), cond("s-5")],
        )
        assert r.summary.unmatched_claim_ids == ["c-1"]
        assert r.summary.insufficient_data_claim_ids == []

    def test_mixed_uncertain_no_match_insufficient(self):
        r = link_stability_conditions(
            [claim("c-1", batch=["BN-X"], comps=["bromobutyl stopper"])],
            [
                cond("s-4", batch="BN-Y", pkg="aluminium cap", cont="PET film"),
                cond("s-5"),
                cond("s-3", pkg="laminate liner"),
            ],
        )
        assert r.summary.uncertain_claim_ids == ["c-1"]
        assert r.summary.uncertain_condition_ids == ["s-3"]
        assert set(r.summary.unlinked_condition_ids) == {"s-4", "s-5"}

    def test_mixed_possible_beats_uncertain(self):
        r = link_stability_conditions(
            [claim("c-1", batch=["BN-1"], comps=["PTFE liner"])],
            [cond("s-a", batch="BN-1"), cond("s-b", pkg="laminate liner")],
        )
        assert r.summary.possible_claim_ids == ["c-1"]
        assert r.summary.linked_condition_ids == ["s-a"]
        assert r.summary.uncertain_condition_ids == ["s-b"]

    def test_condition_linked_once_despite_uncertain_elsewhere(self):
        r = link_stability_conditions(
            [claim("c-1", batch=["BN-1"]), claim("c-2", comps=["PTFE liner"])],
            [cond("s-1", batch="BN-1", pkg="laminate liner")],
        )
        assert r.summary.linked_condition_ids == ["s-1"]
        assert r.summary.uncertain_condition_ids == []

    def test_g23_zero_claims(self):
        r = link_stability_conditions([], [cond("s-1"), cond("s-2")])
        s = r.summary
        assert r.links == []
        assert s.total_claims == 0 and s.total_conditions == 2
        assert s.unlinked_condition_ids == ["s-1", "s-2"]
        assert s.insufficient_data_reasons == {}
        assert_claim_invariant(s)

    def test_g24_zero_conditions(self):
        r = link_stability_conditions([claim("c-1", batch=["BN-1"]), claim("c-2")], [])
        s = r.summary
        assert r.links == []
        assert s.insufficient_data_claim_ids == ["c-1", "c-2"]
        assert s.insufficient_data_reasons == {"c-1": REASON_NO_CONDITIONS, "c-2": REASON_NO_CONDITIONS}
        assert_claim_invariant(s)

    def test_zero_both(self):
        r = link_stability_conditions([], [])
        assert r.links == []
        assert_claim_invariant(r.summary)

    def test_link_counts(self):
        claims, conditions = _five_category_fixture()
        r = link_stability_conditions(claims, conditions)
        s = r.summary
        assert s.confirmed_link_count == sum(l.classification is CONF for l in r.links)
        assert s.possible_link_count == sum(l.classification is POSS for l in r.links)
        assert s.uncertain_link_count == sum(l.classification is UNC for l in r.links)
        assert len(r.links) == s.confirmed_link_count + s.possible_link_count + s.uncertain_link_count


class TestLinkProperties:
    def test_g25_source_refs_preserved(self):
        cl = claim(batch=["BN-1"], comps=["glass vial"], source_id="doc-xyz")
        co = cond(batch="BN-1", pkg="glass vial", source_id="stab-xyz")
        link = single_link(link_stability_conditions([cl], [co]))
        assert link.claim_source_ref == cl.source_ref
        assert link.condition_source_ref == co.source_ref
        assert link.claim_source_ref.source_id == "doc-xyz"
        assert link.condition_source_ref.source_id == "stab-xyz"
        assert isinstance(link.claim_source_ref, SourceReference)

    def test_g26_deterministic_and_sorted(self):
        claims = [claim("c-b", batch=["BN-1"]), claim("c-a", batch=["BN-1"])]
        conditions = [cond("s-2", batch="BN-1"), cond("s-1", batch="BN-1")]
        r1 = link_stability_conditions(claims, conditions)
        r2 = link_stability_conditions(claims, conditions)
        assert r1.links == r2.links
        assert r1.summary == r2.summary
        assert [(l.claim_id, l.condition_id) for l in r1.links] == [
            ("c-a", "s-1"), ("c-a", "s-2"), ("c-b", "s-1"), ("c-b", "s-2")
        ]

    def test_g28_component_note_frozen_and_hashable(self):
        n = compare_component("glass vial", "glass vial")
        assert hash(n) == hash(compare_component("glass vial", "glass vial"))
        with pytest.raises(dataclasses.FrozenInstanceError):
            n.signal_outcome = "x"  # type: ignore[misc]
        assert isinstance(n.shared_material_tokens, tuple)

    def test_g28_link_frozen_tuples(self):
        link = single_link(link_stability_conditions([claim(batch=["BN-1"])], [cond(batch="BN-1")]))
        with pytest.raises(dataclasses.FrozenInstanceError):
            link.strong_signals = ("x",)  # type: ignore[misc]
        for f in (link.strong_signals, link.weak_signals, link.divergent_signals, link.absent_signals,
                  link.component_notes_b, link.component_notes_c):
            assert isinstance(f, tuple)
        assert not hasattr(link.strong_signals, "append")

    def test_g29_signal_completeness(self):
        claims, conditions = _five_category_fixture()
        r = link_stability_conditions(claims, conditions)
        assert r.links
        for link in r.links:
            groups = [set(link.strong_signals), set(link.weak_signals),
                      set(link.divergent_signals), set(link.absent_signals)]
            assert set().union(*groups) == set(ALL_SIGNALS)
            assert sum(len(g) for g in groups) == 3

    def test_g30_notes_non_empty_and_non_regulatory(self):
        claims, conditions = _five_category_fixture()
        r = link_stability_conditions(claims, conditions)
        for link in r.links:
            assert link.notes.strip()
            assert "not a regulatory verdict" in link.notes

    def test_only_emitted_classifications_in_links(self):
        claims, conditions = _five_category_fixture()
        r = link_stability_conditions(claims, conditions)
        for link in r.links:
            assert link.classification in {CONF, POSS, UNC}
