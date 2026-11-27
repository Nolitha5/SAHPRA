"""
RequirementEvidenceLinker for the S.6 Container Closure Agent (Phase 5b).

Implements container_closure.evaluator.RequirementEvidenceLinkerFn:
    Callable[[PassageStatement, Sequence[PassageStatement]], Sequence[PassageStatement]]

Conservative-by-design initial implementation
------------------------------------------------
Shared packaging terminology, the same CTD section, or the same
source document identity do NOT, by themselves, establish that two
statements corroborate the same requirement -- and no other
pharmacist-approved linking rule currently exists. Rather than encode
a partial heuristic that might look defensible without actually being
so, this implementation returns an empty tuple unconditionally: no
statement is ever linked as supporting evidence for another until real
linking criteria are confirmed and a later, separately authorised
phase supplies them.

This is a deliberate, documented no-op, not a placeholder bug. It
never infers corroboration from lexical or structural similarity, and
it never creates an evidence relationship that was not explicitly
established by approved criteria. Trivially compatible with
evaluator.py's existing `_link_supporting_statements` validation
(primary-exclusion / pool-membership / no-duplicates): an empty return
satisfies every one of those rules by construction.
"""
from __future__ import annotations

from typing import Sequence

from container_closure.evaluator import PassageStatement


def link_supporting_statements(
    primary: PassageStatement, pool: Sequence[PassageStatement]  # noqa: ARG001
) -> tuple[PassageStatement, ...]:
    """RequirementEvidenceLinkerFn implementation. Always returns an
    empty tuple -- see module docstring for why."""
    return ()
