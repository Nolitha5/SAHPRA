"""
Port interfaces (Protocols) for the S.6 Container Closure Agent.

These are OUR contracts, expressed entirely in terms of our own Pydantic
models.  When M2, M3 and M4b interfaces are confirmed, thin adapter
modules will implement these protocols against the real external APIs
without touching this file or any evaluation logic.

Design rules
------------
* Every protocol is a typing.Protocol (structural sub-typing) so that
  mock implementations used in tests can satisfy them without
  inheriting from any base class.
* No protocol here assumes anything about the wire format, transport
  protocol, process boundary or concurrency model of the external
  dependency.  Those are adapter concerns.
* Protocols deal only in models already defined in shared.models.
  No new data contracts are introduced here.
* All methods are synchronous.  Async support is deferred until
  there is a confirmed need.
* All query methods may raise PortError (see below) for any failure
  that prevents them from returning a useful result. Callers (the
  evaluator) must handle PortError and produce an INSUFFICIENT_DATA
  finding rather than propagating it up.
"""
from __future__ import annotations

from typing import Protocol, Sequence

from shared.exceptions import S6BaseError
from shared.models import RKBRequirement, S6Claim, S7StabilityCondition


# ---------------------------------------------------------------------------
# Port-level exception
# ---------------------------------------------------------------------------


class PortError(S6BaseError):
    """Raised by any Port implementation when it cannot fulfil a
    query -- e.g. the backing service is unreachable, returned a
    malformed response, or returned no results for a reason that
    prevents the evaluator from reaching a verdict.

    Callers MUST catch PortError and produce INSUFFICIENT_DATA
    findings rather than letting it propagate.
    """


# ---------------------------------------------------------------------------
# Protocol definitions
# ---------------------------------------------------------------------------


class ClaimSource(Protocol):
    """Provides S.6 packaging claims extracted from the sponsor
    dossier (supplied by M3).  One implementation per session."""

    def get_claims(self, session_id: str) -> Sequence[S6Claim]:
        """Return all S.6 claims for the given session.

        Raises
        ------
        PortError
            If the claims cannot be retrieved (e.g. M3 extraction has
            not completed, the session is unknown, or M3 is
            unavailable).
        """
        ...


class RequirementSource(Protocol):
    """Retrieves applicable ICH guideline requirements from M2's
    Regulatory Knowledge Base for a given packaging topic."""

    def get_requirements(self, topic: str) -> Sequence[RKBRequirement]:
        """Return requirements relevant to `topic`.

        Parameters
        ----------
        topic:
            Free-text topic drawn from an S6Claim (e.g. a packaging
            component name, storage descriptor, or compliance keyword).
            The implementation decides how to map this to an RKB query.

        Returns
        -------
        Sequence[RKBRequirement]
            Zero or more requirements. An empty list is a valid result
            (no applicable requirement found); the evaluator must then
            produce INSUFFICIENT_DATA for the corresponding finding.

        Raises
        ------
        PortError
            If the RKB itself is unavailable or the query failed in a
            way that prevents any result from being returned.
        """
        ...


class StabilitySource(Protocol):
    """Provides S.7 stability conditions for cross-reference against
    S.6 packaging claims (supplied by M4b)."""

    def get_stability_conditions(
        self, session_id: str
    ) -> Sequence[S7StabilityCondition]:
        """Return S.7 stability conditions for the given session.

        Raises
        ------
        PortError
            If M4b has not yet produced stability conditions for this
            session, or M4b is unavailable.
        """
        ...
