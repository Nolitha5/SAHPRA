"""
Synthetic test fixtures for the S.6 Container Closure Agent (Phase 4a).

All objects here are constructed entirely from our own Pydantic contracts
(S6Claim, RKBRequirement, S7StabilityCondition) and in-memory mock
implementations of the port protocols (ClaimSource, RequirementSource,
StabilitySource).

Rules
-----
* No external service is called.  Everything is in-memory.
* No regulatory content is invented.  RKBRequirement text is clearly
  labelled as synthetic test data to prevent any confusion.
* fixture_ prefix on factories; mock_ prefix on mock port classes.
* Every claim that is meant to be valid satisfies all four parser
  hard-checks (R1-R4).
"""
from __future__ import annotations

from shared.models import (
    RKBRequirement,
    S6Claim,
    S7StabilityCondition,
    SourceReference,
)
from container_closure.ports import (
    ClaimSource,
    PortError,
    RequirementSource,
    StabilitySource,
)


# ---------------------------------------------------------------------------
# SourceReference helpers
# ---------------------------------------------------------------------------


def fixture_source_ref(
    source_type: str = "m3_extraction",
    source_id: str = "doc-001",
    section: str = "S.6",
    document: str | None = "test_dossier.pdf",
    page: int | None = 12,
) -> SourceReference:
    return SourceReference(
        source_type=source_type,
        source_id=source_id,
        section=section,
        document=document,
        page=page,
    )


def fixture_rkb_source_ref(
    source_id: str = "rkb-req-001",
    guideline: str = "ICH_Q6A",
) -> SourceReference:
    return SourceReference(
        source_type="m2_rkb",
        source_id=source_id,
        section="TEST",
        document=guideline,
    )


def fixture_stability_source_ref(source_id: str = "stability-001") -> SourceReference:
    return SourceReference(
        source_type="m4b_stability",
        source_id=source_id,
        section="S.7",
        document="test_stability_data.pdf",
    )


# ---------------------------------------------------------------------------
# S6Claim factories
# ---------------------------------------------------------------------------


def fixture_valid_claim(
    claim_id: str = "c-001",
    text: str = "The container is a 10 mL Type I borosilicate glass vial with a bromobutyl rubber stopper.",
    packaging_components: list[str] | None = None,
    batch_numbers: list[str] | None = None,
    quantitative_values: dict[str, str] | None = None,
) -> S6Claim:
    """A minimal but fully valid S6Claim that passes all parser checks."""
    return S6Claim(
        claim_id=claim_id,
        text=text,
        source_ref=fixture_source_ref(),
        packaging_components=packaging_components or ["Type I glass vial", "bromobutyl rubber stopper"],
        batch_numbers=batch_numbers or ["BN-2024-001"],
        quantitative_values=quantitative_values or {"volume_mL": "10"},
    )


def fixture_claim_empty_id() -> S6Claim:
    """Claim with whitespace-only claim_id — rejected by parser (R1)."""
    return S6Claim(
        claim_id="   ",
        text="Some container text",
        source_ref=fixture_source_ref(),
    )


def fixture_claim_empty_text() -> S6Claim:
    """Claim with whitespace-only text — rejected by parser (R2)."""
    return S6Claim(
        claim_id="c-empty-text",
        text="   ",
        source_ref=fixture_source_ref(),
    )


def fixture_claim_bad_source_ref_no_type() -> S6Claim:
    """Claim whose source_ref has empty source_type — rejected (R3)."""
    return S6Claim(
        claim_id="c-bad-src",
        text="Container is a glass vial.",
        source_ref=SourceReference(
            source_type="",
            source_id="doc-001",
            section="S.6",
        ),
    )


def fixture_claim_bad_source_ref_no_id() -> S6Claim:
    """Claim whose source_ref has whitespace-only source_id — rejected (R3)."""
    return S6Claim(
        claim_id="c-bad-src-id",
        text="Container is a glass vial.",
        source_ref=SourceReference(
            source_type="m3_extraction",
            source_id="   ",
            section="S.6",
        ),
    )


def fixture_claim_wrong_section() -> S6Claim:
    """Claim with section='P.3' — rejected (R4)."""
    return S6Claim(
        claim_id="c-wrong-section",
        text="Manufacturing process description.",
        source_ref=fixture_source_ref(section="P.3"),
        section="P.3",
    )


def fixture_claim_minimal_optional_fields() -> S6Claim:
    """Valid claim with no optional list/dict fields populated.

    Should be ACCEPTED by the parser; downstream evaluator will
    produce INSUFFICIENT_DATA findings for the missing fields.
    """
    return S6Claim(
        claim_id="c-minimal",
        text="Container closure details to be determined.",
        source_ref=fixture_source_ref(),
    )


def fixture_claim_with_stability_reference() -> S6Claim:
    """Valid claim that explicitly references a stability packaging item,
    enabling S.6/S.7 cross-reference by the evaluator (Phase 4b)."""
    return S6Claim(
        claim_id="c-stability-ref",
        text="The HDPE bottle with polypropylene cap was used in the 24-month stability study.",
        source_ref=fixture_source_ref(source_id="doc-001-p15", page=15),
        packaging_components=["HDPE bottle", "polypropylene cap"],
        batch_numbers=["BN-2024-002"],
        quantitative_values={"study_duration_months": "24"},
    )


# ---------------------------------------------------------------------------
# RKBRequirement factories
# ---------------------------------------------------------------------------


def fixture_rkb_requirement(
    requirement_id: str = "req-001",
    guideline: str = "ICH_Q6A_TEST",
    section: str = "5.1",
    text: str = "[SYNTHETIC TEST DATA] Packaging materials must be of appropriate quality.",
    citation: str = "[SYNTHETIC] ICH Q6A Test Section 5.1",
) -> RKBRequirement:
    """A clearly synthetic RKB requirement for testing only.

    Text and citation are labelled '[SYNTHETIC TEST DATA]' to prevent
    any confusion with real regulatory content.
    """
    return RKBRequirement(
        requirement_id=requirement_id,
        guideline=guideline,
        section=section,
        text=text,
        citation=citation,
        source_ref=fixture_rkb_source_ref(source_id=requirement_id, guideline=guideline),
    )


# ---------------------------------------------------------------------------
# S7StabilityCondition factories
# ---------------------------------------------------------------------------


def fixture_stability_condition(
    condition_id: str = "sc-001",
    storage_condition: str = "25°C / 60% RH",
    container_reference: str | None = "Type I glass vial",
    batch_number: str | None = "BN-2024-001",
    packaging_reference: str | None = "Type I glass vial / bromobutyl rubber stopper",
) -> S7StabilityCondition:
    return S7StabilityCondition(
        condition_id=condition_id,
        storage_condition=storage_condition,
        container_reference=container_reference,
        batch_number=batch_number,
        packaging_reference=packaging_reference,
        source_ref=fixture_stability_source_ref(),
    )


def fixture_stability_condition_no_packaging_ref() -> S7StabilityCondition:
    """Stability condition with no packaging_reference — evaluator
    cannot cross-reference against S.6; yields INSUFFICIENT_DATA."""
    return S7StabilityCondition(
        condition_id="sc-no-pkg",
        storage_condition="40°C / 75% RH (accelerated)",
        container_reference=None,
        batch_number="BN-2024-003",
        packaging_reference=None,
        source_ref=fixture_stability_source_ref(source_id="stability-002"),
    )


# ---------------------------------------------------------------------------
# In-memory mock port implementations
# ---------------------------------------------------------------------------


class MockClaimSource:
    """In-memory ClaimSource.  Satisfies the ClaimSource Protocol."""

    def __init__(
        self,
        claims: list[S6Claim] | None = None,
        *,
        raise_port_error: bool = False,
    ) -> None:
        self._claims: list[S6Claim] = claims if claims is not None else []
        self._raise = raise_port_error

    def get_claims(self, session_id: str) -> list[S6Claim]:  # noqa: ARG002
        if self._raise:
            raise PortError("MockClaimSource: simulated M3 unavailability")
        return list(self._claims)


class MockRequirementSource:
    """In-memory RequirementSource.  Returns a fixed list of requirements
    regardless of topic (sufficient for unit tests)."""

    def __init__(
        self,
        requirements: list[RKBRequirement] | None = None,
        *,
        raise_port_error: bool = False,
    ) -> None:
        self._requirements: list[RKBRequirement] = (
            requirements if requirements is not None else []
        )
        self._raise = raise_port_error

    def get_requirements(self, topic: str) -> list[RKBRequirement]:  # noqa: ARG002
        if self._raise:
            raise PortError("MockRequirementSource: simulated M2 unavailability")
        return list(self._requirements)


class MockStabilitySource:
    """In-memory StabilitySource."""

    def __init__(
        self,
        conditions: list[S7StabilityCondition] | None = None,
        *,
        raise_port_error: bool = False,
    ) -> None:
        self._conditions: list[S7StabilityCondition] = (
            conditions if conditions is not None else []
        )
        self._raise = raise_port_error

    def get_stability_conditions(
        self, session_id: str
    ) -> list[S7StabilityCondition]:  # noqa: ARG002
        if self._raise:
            raise PortError("MockStabilitySource: simulated M4b unavailability")
        return list(self._conditions)
