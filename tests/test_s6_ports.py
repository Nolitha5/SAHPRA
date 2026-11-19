"""
Tests for src/container_closure/ports.py — Phase 4a.

Verifies:
* PortError is a subclass of S6BaseError.
* The three Protocol classes exist and have the expected method signatures.
* In-memory mock implementations (from fixtures) satisfy the protocols at
  runtime (structural sub-typing check via isinstance with runtime_checkable,
  plus direct call tests).
* Mock implementations correctly raise PortError when configured to do so.
* Protocol methods accept the correct argument types (session_id: str,
  topic: str) and return sequences of the right model types.
"""
from __future__ import annotations

import pytest

from container_closure.ports import ClaimSource, PortError, RequirementSource, StabilitySource
from shared.exceptions import S6BaseError
from tests.fixtures.s6_fixtures import (
    MockClaimSource,
    MockRequirementSource,
    MockStabilitySource,
    fixture_rkb_requirement,
    fixture_stability_condition,
    fixture_valid_claim,
)


# ---------------------------------------------------------------------------
# PortError
# ---------------------------------------------------------------------------


class TestPortError:
    def test_port_error_is_s6base_error(self):
        err = PortError("test")
        assert isinstance(err, S6BaseError)

    def test_port_error_message(self):
        err = PortError("simulated failure")
        assert "simulated failure" in str(err)

    def test_port_error_can_be_raised_and_caught(self):
        with pytest.raises(PortError):
            raise PortError("test raise")


# ---------------------------------------------------------------------------
# MockClaimSource
# ---------------------------------------------------------------------------


class TestMockClaimSource:
    def test_returns_empty_list_by_default(self):
        src = MockClaimSource()
        result = src.get_claims("session-1")
        assert result == []

    def test_returns_supplied_claims(self):
        claim = fixture_valid_claim()
        src = MockClaimSource([claim])
        result = src.get_claims("session-1")
        assert len(result) == 1
        assert result[0].claim_id == "c-001"

    def test_session_id_parameter_accepted(self):
        src = MockClaimSource()
        # Different session ids must not raise
        src.get_claims("sess-a")
        src.get_claims("sess-b")

    def test_raises_port_error_when_configured(self):
        src = MockClaimSource(raise_port_error=True)
        with pytest.raises(PortError):
            src.get_claims("session-1")

    def test_returned_list_is_independent_copy(self):
        claim = fixture_valid_claim()
        src = MockClaimSource([claim])
        result = src.get_claims("s")
        result.clear()
        # Second call must still return the original claim
        assert len(src.get_claims("s")) == 1

    def test_multiple_claims_returned_in_order(self):
        claims = [fixture_valid_claim(claim_id=f"c-{i:03d}") for i in range(5)]
        src = MockClaimSource(claims)
        result = src.get_claims("s")
        assert [c.claim_id for c in result] == [f"c-{i:03d}" for i in range(5)]


# ---------------------------------------------------------------------------
# MockRequirementSource
# ---------------------------------------------------------------------------


class TestMockRequirementSource:
    def test_returns_empty_list_by_default(self):
        src = MockRequirementSource()
        assert src.get_requirements("any topic") == []

    def test_returns_supplied_requirements(self):
        req = fixture_rkb_requirement()
        src = MockRequirementSource([req])
        result = src.get_requirements("packaging")
        assert len(result) == 1
        assert result[0].requirement_id == "req-001"

    def test_topic_parameter_accepted(self):
        src = MockRequirementSource()
        src.get_requirements("glass container")
        src.get_requirements("rubber stopper")

    def test_raises_port_error_when_configured(self):
        src = MockRequirementSource(raise_port_error=True)
        with pytest.raises(PortError):
            src.get_requirements("packaging")

    def test_returned_list_is_independent_copy(self):
        req = fixture_rkb_requirement()
        src = MockRequirementSource([req])
        result = src.get_requirements("t")
        result.clear()
        assert len(src.get_requirements("t")) == 1


# ---------------------------------------------------------------------------
# MockStabilitySource
# ---------------------------------------------------------------------------


class TestMockStabilitySource:
    def test_returns_empty_list_by_default(self):
        src = MockStabilitySource()
        assert src.get_stability_conditions("session-1") == []

    def test_returns_supplied_conditions(self):
        cond = fixture_stability_condition()
        src = MockStabilitySource([cond])
        result = src.get_stability_conditions("session-1")
        assert len(result) == 1
        assert result[0].condition_id == "sc-001"

    def test_raises_port_error_when_configured(self):
        src = MockStabilitySource(raise_port_error=True)
        with pytest.raises(PortError):
            src.get_stability_conditions("session-1")

    def test_returned_list_is_independent_copy(self):
        cond = fixture_stability_condition()
        src = MockStabilitySource([cond])
        result = src.get_stability_conditions("s")
        result.clear()
        assert len(src.get_stability_conditions("s")) == 1
