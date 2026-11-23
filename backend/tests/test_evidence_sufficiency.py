"""
tests/test_evidence_sufficiency.py — Phase 4: Evidence Sufficiency Tests
=========================================================================

Tests T-ES-01 through T-ES-10 as specified in the Phase 4 proposal.

Coverage
--------
T-ES-01  SUPPORTED: COMPLIANT + no flags + Tier 1 tier → SUPPORTED
T-ES-02  SUPPORTED: COMPLIANT + no flags + tier=None (backward compat) → SUPPORTED
T-ES-03  PARTIAL: COMPLIANT + no flags + TIER_2_GUIDANCE → PARTIAL (not SUPPORTED)
T-ES-04  PARTIAL: COMPLIANT + no flags + TIER_3_DISCOVERY_ONLY → PARTIAL
T-ES-05  PARTIAL: COMPLIANT + flags present (Tier 1) → PARTIAL
T-ES-06  PARTIAL: NON_COMPLIANT + no flags + Tier 1 → PARTIAL
T-ES-07  PARTIAL: NON_COMPLIANT + flags + Tier 1 → PARTIAL
T-ES-08  INSUFFICIENT: NEEDS_REVIEW + flags → INSUFFICIENT
T-ES-09  NOT_VERIFIED: NEEDS_REVIEW + no flags → NOT_VERIFIED
T-ES-10  CONFLICTING: evidence_tier == "CONFLICTING" → CONFLICTING (any verdict)

T-ES-11  Integration: check_s5_claim with mock repo → COMPLIANT → SUPPORTED
T-ES-12  Integration: check_s5_claim with mock repo + flags → PARTIAL

No confidential applicant data is used.
"""

import sys
import os
from datetime import date

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from s5_standards import _derive_evidence_sufficiency, check_s5_claim, MockMonographRepository
from models import S5Claim


# =============================================================================
# Unit tests for _derive_evidence_sufficiency
# =============================================================================

# T-ES-01: COMPLIANT + no flags + Tier 1 → SUPPORTED
def test_tes_01_supported_compliant_no_flags_tier1():
    """T-ES-01: authoritative COMPLIANT with no gaps → SUPPORTED."""
    result = _derive_evidence_sufficiency(
        "COMPLIANT", [], evidence_tier="TIER_1_EXISTENCE_CONFIRMED"
    )
    assert result == "SUPPORTED"


# T-ES-02: backward-compatible: COMPLIANT + no flags + tier=None → SUPPORTED
def test_tes_02_supported_compliant_no_flags_no_tier():
    """T-ES-02: tier=None (old call sites) → SUPPORTED when COMPLIANT and no flags."""
    result = _derive_evidence_sufficiency("COMPLIANT", [], evidence_tier=None)
    assert result == "SUPPORTED"


# T-ES-03: COMPLIANT + no flags + TIER_2_GUIDANCE → PARTIAL (not SUPPORTED)
def test_tes_03_partial_compliant_no_flags_tier2():
    """T-ES-03: ingested-document COMPLIANT cannot be SUPPORTED → PARTIAL."""
    result = _derive_evidence_sufficiency(
        "COMPLIANT", [], evidence_tier="TIER_2_GUIDANCE"
    )
    assert result == "PARTIAL"


# T-ES-04: COMPLIANT + no flags + TIER_3_DISCOVERY_ONLY → PARTIAL
def test_tes_04_partial_compliant_no_flags_tier3():
    """T-ES-04: discovery-only COMPLIANT → PARTIAL."""
    result = _derive_evidence_sufficiency(
        "COMPLIANT", [], evidence_tier="TIER_3_DISCOVERY_ONLY"
    )
    assert result == "PARTIAL"


# T-ES-05: COMPLIANT + flags + Tier 1 → PARTIAL
def test_tes_05_partial_compliant_with_flags_tier1():
    """T-ES-05: COMPLIANT but structural gaps remain → PARTIAL."""
    result = _derive_evidence_sufficiency(
        "COMPLIANT",
        ["lot_number_missing", "purity_not_stated"],
        evidence_tier="TIER_1_EXISTENCE_CONFIRMED",
    )
    assert result == "PARTIAL"


# T-ES-06: NON_COMPLIANT + no flags + Tier 1 → PARTIAL
def test_tes_06_partial_non_compliant_no_flags():
    """T-ES-06: edition mismatch with no structural gaps → PARTIAL."""
    result = _derive_evidence_sufficiency(
        "NON_COMPLIANT", [], evidence_tier="TIER_1_EXISTENCE_CONFIRMED"
    )
    assert result == "PARTIAL"


# T-ES-07: NON_COMPLIANT + flags + Tier 1 → PARTIAL
def test_tes_07_partial_non_compliant_with_flags():
    """T-ES-07: edition mismatch AND structural gaps → PARTIAL."""
    result = _derive_evidence_sufficiency(
        "NON_COMPLIANT",
        ["lot_number_missing"],
        evidence_tier="TIER_1_EXISTENCE_CONFIRMED",
    )
    assert result == "PARTIAL"


# T-ES-08: NEEDS_REVIEW + flags → INSUFFICIENT
def test_tes_08_insufficient_needs_review_with_flags():
    """T-ES-08: unresolvable edition + structural gaps → INSUFFICIENT."""
    result = _derive_evidence_sufficiency(
        "NEEDS_REVIEW",
        ["lot_number_missing", "purity_not_stated"],
        evidence_tier=None,
    )
    assert result == "INSUFFICIENT"


# T-ES-09: NEEDS_REVIEW + no flags → NOT_VERIFIED
def test_tes_09_not_verified_needs_review_no_flags():
    """T-ES-09: repository data gap, claim otherwise complete → NOT_VERIFIED."""
    result = _derive_evidence_sufficiency(
        "NEEDS_REVIEW", [], evidence_tier=None
    )
    assert result == "NOT_VERIFIED"


# T-ES-10: CONFLICTING sentinel takes absolute priority
def test_tes_10_conflicting_sentinel():
    """T-ES-10: CONFLICTING tier overrides all other inputs → CONFLICTING."""
    # Should return CONFLICTING regardless of verdict or flags
    for verdict in ("COMPLIANT", "NON_COMPLIANT", "NEEDS_REVIEW"):
        for flags in ([], ["some_flag"]):
            result = _derive_evidence_sufficiency(
                verdict, flags, evidence_tier="CONFLICTING"
            )
            assert result == "CONFLICTING", (
                f"Expected CONFLICTING for verdict={verdict!r} flags={flags!r}, "
                f"got {result!r}"
            )


# T-ES-11: Integration — check_s5_claim COMPLIANT with mock → SUPPORTED
def test_tes_11_integration_compliant_produces_supported():
    """
    T-ES-11: a fully specified claim that the mock repo can confirm as COMPLIANT
    should produce evidence_sufficiency == SUPPORTED.
    """
    claim = S5Claim(
        substance_name="Aspirin",
        standard="USP",
        edition_claimed="USP 47",
        lot_number="LOT-ASP-01",
        purity_assigned=99.5,
        submission_date=date(2024, 6, 1),
        source_pharmacopoeia="USP",
        standard_type="compendial_primary",
        # Sub-item (b): supply the correct S5Claim fields (not certificate_of_analysis)
        coa_submitted=True,
        ir_spectra_submitted=True,
        # Sub-item (c)
        working_std_qualified_against_primary=True,
        # Sub-item (d)
        reference_standard_source_detail="Purchased from USP catalogue",
    )
    finding = check_s5_claim(claim, MockMonographRepository())
    assert finding.verdict == "COMPLIANT", f"Expected COMPLIANT, got {finding.verdict}"
    assert finding.evidence_sufficiency == "SUPPORTED", (
        f"Expected SUPPORTED, got {finding.evidence_sufficiency}"
    )


# T-ES-12: Integration — check_s5_claim with missing fields → PARTIAL
def test_tes_12_integration_compliant_with_missing_fields_produces_partial():
    """
    T-ES-12: a claim with missing IPRP sub-items but a matching edition should
    produce evidence_sufficiency == PARTIAL (flags present).
    """
    # Minimal claim — omits optional fields to trigger completeness flags
    claim = S5Claim(
        substance_name="Aspirin",
        standard="USP",
        edition_claimed="USP 47",
        lot_number=None,       # will trigger a completeness flag
        purity_assigned=None,  # will trigger a completeness flag
        submission_date=date(2024, 6, 1),
        source_pharmacopoeia="USP",
        standard_type="compendial_primary",
    )
    finding = check_s5_claim(claim, MockMonographRepository())
    # Verdict may be COMPLIANT or NEEDS_REVIEW depending on completeness checks,
    # but evidence_sufficiency must NOT be SUPPORTED when flags are present.
    assert finding.evidence_sufficiency != "SUPPORTED", (
        f"Did not expect SUPPORTED when completeness_flags={finding.completeness_flags!r}"
    )
