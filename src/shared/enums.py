"""
Shared enumerations for the Container Closure Agent S6 project.

These back the corresponding TEXT columns in shared/schema.py and the
corresponding fields in shared/models.py. Enum values are the exact
strings persisted in the database, so changing a value here is a
schema-affecting change, not a cosmetic one.
"""
from __future__ import annotations

from enum import Enum


class AgentName(str, Enum):
    """All specialist agents whose findings may appear in the shared
    audit log, plus the cross-section consistency agent. This list
    reflects the 11 specialist agents named in the Member 4a
    specification's "support findings from all 11 specialist agents"
    requirement, plus our own two agents.
    """
    S1_GENERAL_INFO = "s1_general_info"
    S2_MANUFACTURE = "s2_manufacture"
    S3_CHARACTERISATION = "s3_characterisation"
    S4_CONTROL = "s4_control"
    S5_REFERENCE_STDS = "s5_reference_standards"
    S6_CONTAINER_CLOSURE = "s6_container_closure"
    S7_STABILITY = "s7_stability"
    P1_DESCRIPTION = "p1_description"
    P2_DEVELOPMENT = "p2_development"
    P3_MANUFACTURE = "p3_manufacture"
    P8_STABILITY = "p8_stability"
    CROSS_SECTION = "cross_section_consistency"


class Verdict(str, Enum):
    """Compliance verdict for a finding."""
    COMPLIANT = "COMPLIANT"
    NON_COMPLIANT = "NON_COMPLIANT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class Severity(str, Enum):
    """Severity assigned to a finding."""
    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    MINOR = "MINOR"
    INFO = "INFO"


class FindingType(str, Enum):
    """Distinguishes an ordinary compliance finding from a
    cross-section contradiction finding. Both share the same
    `findings` table and the same FindingRecord contract."""
    COMPLIANCE = "compliance"
    CONTRADICTION = "contradiction"


class DecisionOutcome(str, Enum):
    """The regulatory/assessor action taken at a Human Gate."""
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REFERRED = "REFERRED"
    ADDITIONAL_INFO = "ADDITIONAL_INFO"
    DEFERRED = "DEFERRED"
    OVERRIDDEN = "OVERRIDDEN"


class EventStatus(str, Enum):
    """Lifecycle status of an audit event."""
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"


class ComparisonFieldType(str, Enum):
    """The set of comparison types the Cross-Section Consistency
    Agent is permitted to flag a contradiction on. Deliberately
    closed (not free text) so that `comparators.py` (implemented in
    a later phase) and this enum cannot silently drift apart."""
    BATCH_NUMBER = "batch_number"
    DATE = "date"
    QUANTITY = "quantity"
    PACKAGING_REFERENCE = "packaging_reference"
