"""
Tests for src/container_closure/evidence_linker.py (Phase 5b).

The implementation is a deliberate, always-empty no-op (see its module
docstring for why). These tests prove the no-op holds even in cases
that might look "obviously linkable" -- shared terminology, same CTD
section, same source document -- precisely because none of those are
actually defensible grounds yet.
"""
from __future__ import annotations

from container_closure.evaluator import (
    PassageInterpretation,
    PassageStatement,
    RetrievedPassage,
    _link_supporting_statements,
)
from container_closure.evidence_linker import link_supporting_statements
from shared.models import SourceReference


def _passage(passage_id: str, text: str, document_id: str = "doc-001") -> RetrievedPassage:
    return RetrievedPassage(
        passage_id=passage_id,
        originating_question_id="q-el-001",
        ctd_section="3.2.S.6",
        text=text,
        source_ref=SourceReference(source_type="m2_rkb", source_id=passage_id, section="3.2.S.6"),
        document_id=document_id,
    )


def _statement(
    passage: RetrievedPassage,
    text: str | None = None,
    interpretation: PassageInterpretation = PassageInterpretation.SUPPORTING_INFORMATION,
) -> PassageStatement:
    stmt_text = text if text is not None else passage.text
    return PassageStatement(
        statement_text=stmt_text,
        source_passage=passage,
        interpretation=interpretation,
        boundary_confidence="confident",
        span=None,
    )


class TestAlwaysReturnsEmpty:
    def test_empty_pool(self) -> None:
        p = _passage("p1", "[SYNTHETIC TEST DATA] Type I glass vial text.")
        primary = _statement(p)
        assert link_supporting_statements(primary, []) == ()

    def test_single_item_pool(self) -> None:
        p = _passage("p1", "[SYNTHETIC TEST DATA] Type I glass vial text.")
        p2 = _passage("p2", "[SYNTHETIC TEST DATA] Another vial statement.")
        primary = _statement(p)
        candidate = _statement(p2)
        assert link_supporting_statements(primary, [candidate]) == ()

    def test_shared_packaging_terminology_is_not_sufficient(self) -> None:
        p = _passage("p1", "[SYNTHETIC TEST DATA] Type I glass vial with chlorobutyl stopper.")
        p2 = _passage("p2", "[SYNTHETIC TEST DATA] Type I glass vial with chlorobutyl stopper, again.")
        primary = _statement(p)
        candidate = _statement(p2)
        assert link_supporting_statements(primary, [candidate]) == ()

    def test_same_ctd_section_is_not_sufficient(self) -> None:
        p = _passage("p1", "[SYNTHETIC TEST DATA] Statement A.")
        p2 = _passage("p2", "[SYNTHETIC TEST DATA] Statement B.")
        assert p.ctd_section == p2.ctd_section == "3.2.S.6"
        primary = _statement(p)
        candidate = _statement(p2)
        assert link_supporting_statements(primary, [candidate]) == ()

    def test_same_source_document_is_not_sufficient(self) -> None:
        p = _passage("p1", "[SYNTHETIC TEST DATA] Statement A.", document_id="doc-shared")
        p2 = _passage("p2", "[SYNTHETIC TEST DATA] Statement B.", document_id="doc-shared")
        primary = _statement(p)
        candidate = _statement(p2)
        assert link_supporting_statements(primary, [candidate]) == ()

    def test_multiple_tempting_candidates_still_yields_empty(self) -> None:
        p = _passage("p1", "[SYNTHETIC TEST DATA] Closure integrity statement.", document_id="doc-shared")
        candidates = [
            _statement(_passage(f"p{i}", "[SYNTHETIC TEST DATA] Closure integrity statement.", document_id="doc-shared"))
            for i in range(2, 6)
        ]
        primary = _statement(p)
        assert link_supporting_statements(primary, candidates) == ()


class TestCompatibilityWithEvaluatorValidation:
    def test_compatible_with_evaluators_own_link_validation_helper(self) -> None:
        """An empty return trivially satisfies every one of
        _link_supporting_statements's own rules (primary-exclusion,
        pool-membership, no-duplicates) -- no dropped-candidate detail
        is ever produced."""
        p = _passage("p1", "[SYNTHETIC TEST DATA] Primary statement text.")
        p2 = _passage("p2", "[SYNTHETIC TEST DATA] Pool statement text.")
        primary = _statement(p)
        pool = [_statement(p2)]

        accepted, detail = _link_supporting_statements(primary, pool, link_supporting_statements)
        assert accepted == ()
        assert detail == {}
