"""
S.2 Manufacture agent.

Reviews the manufacture section of a drug-substance dossier (3.2.S.2) for
completeness and internal consistency, per the IPRP QWGG Guidance for
Quality Assessors (Drug Substance) and ICH M4Q structure:

  S.2.1  Manufacturer(s)
  S.2.2  Description of Manufacturing Process and Process Controls
  S.2.3  Control of Materials
  S.2.4  Controls of Critical Steps and Intermediates
  S.2.5  Process Validation and/or Evaluation
  S.2.6  Manufacturing Process Development

This agent does NOT make regulatory judgements. It produces structured
Finding objects (completeness gaps, internal-consistency flags, and risks
that link forward to S.3/S.4) for the human assessor, via the QA/Critic and
Orchestrator. All findings carry requires_human_review=True and
qa_status=PENDING.
"""
from __future__ import annotations

import re

from .agents_common import (
    chunks_in_section,
    evidence_from_chunk,
    is_subsection,
    make_finding_id,
    missing_subsection_finding,
    present_subsections,
)
from .schemas import DossierChunk, Finding, FindingStatus

AGENT_ID = "S2_MANUFACTURE"

# Required S.2 subsections. S.2.5 (process validation) is only normally
# required for sterile/aseptic substances per IPRP guidance, so its absence
# is a lower-uncertainty informational flag rather than a hard gap.
_REQUIRED_SUBSECTIONS = {
    "3.2.S.2.1": "Manufacturer(s)",
    "3.2.S.2.2": "Description of Manufacturing Process and Process Controls",
    "3.2.S.2.3": "Control of Materials",
    "3.2.S.2.4": "Controls of Critical Steps and Intermediates",
    "3.2.S.2.6": "Manufacturing Process Development",
}

# Cues used for light internal-consistency checks on the process description.
_ADDRESS_CUES = re.compile(
    r"\b(?:[\w-]+\s+(?:street|road|avenue|boulevard|lane|drive)|"
    r"(?:plot|block|unit)\s+[A-Z0-9-]+)\b", re.I,
)
_FLOW_CUES = re.compile(r"\b(?:flow\s*(?:diagram|chart)|(?:reaction|process|synthetic)\s+scheme)\b", re.I)
_STARTING_MATERIAL_CUES = re.compile(r"\b(starting material|raw material|reagent|solvent|catalyst)\b", re.I)


def _subsection_text(chunks: list[DossierChunk], code: str) -> str:
    return " ".join(c.text for c in chunks if is_subsection(c, code))


def review(case_id: str, chunks: list[DossierChunk]) -> list[Finding]:
    """Run the S.2 Manufacture review over a case's dossier chunks."""
    s2 = chunks_in_section(chunks, "3.2.S.2")
    findings: list[Finding] = []

    # Nothing attributed to S.2 at all -> single MISSING_INFORMATION finding.
    if not s2:
        findings.append(
            Finding(
                finding_id=make_finding_id(AGENT_ID, case_id, "no-s2"),
                case_id=case_id,
                agent_id=AGENT_ID,
                ctd_section="3.2.S.2",
                issue_type="section_absent",
                status=FindingStatus.MISSING_INFORMATION,
                rationale=(
                    "No content was attributed to section 3.2.S.2 "
                    "(Manufacture) during ingestion. The Manufacture section "
                    "could not be located or recognised; assessor must confirm."
                ),
                uncertainty=0.6,
                attributes={"check": "completeness"},
            )
        )
        return findings

    present = present_subsections(s2)
    sibling_evidence = [evidence_from_chunk(c) for c in s2[:2]]

    # 1. Completeness: required subsections present?
    for code, title in _REQUIRED_SUBSECTIONS.items():
        if code not in present:
            findings.append(
                missing_subsection_finding(AGENT_ID, case_id, code, title, sibling_evidence)
            )

    # S.2.5 — only flagged informationally (sterile-dependent).
    if "3.2.S.2.5" not in present:
        findings.append(
            Finding(
                finding_id=make_finding_id(AGENT_ID, case_id, "s25-info"),
                case_id=case_id,
                agent_id=AGENT_ID,
                ctd_section="3.2.S.2.5",
                issue_type="conditional_subsection_absent",
                status=FindingStatus.POTENTIAL_GAP,
                sponsor_evidence=sibling_evidence,
                rationale=(
                    "No 3.2.S.2.5 (Process Validation/Evaluation) content found. "
                    "This is normally required only for sterile/aseptically "
                    "processed substances. Assessor to confirm whether the "
                    "substance is sterile and, if so, whether validation is present."
                ),
                uncertainty=0.4,
                attributes={"check": "completeness", "conditional": "sterile_only"},
            )
        )

    # 2. Consistency checks on S.2.1 (manufacturer address present?)
    s21_text = _subsection_text(s2, "3.2.S.2.1")
    if s21_text and not _ADDRESS_CUES.search(s21_text):
        s21_chunks = [c for c in s2 if is_subsection(c, "3.2.S.2.1")]
        findings.append(
            Finding(
                finding_id=make_finding_id(AGENT_ID, case_id, "s21-no-address"),
                case_id=case_id,
                agent_id=AGENT_ID,
                ctd_section="3.2.S.2.1",
                issue_type="possible_missing_address",
                status=FindingStatus.POTENTIAL_GAP,
                sponsor_evidence=[evidence_from_chunk(c) for c in s21_chunks[:2]],
                rationale=(
                    "3.2.S.2.1 is present but no manufacturer site address was "
                    "detected. IPRP guidance requires the actual site address "
                    "(unit/plot/block), not the administrative office. Assessor "
                    "to verify a full manufacturing address is stated."
                ),
                uncertainty=0.55,
                attributes={"check": "consistency", "cue": "address"},
            )
        )

    # 3. S.2.2 process description — flow diagram / route cues present?
    s22_text = _subsection_text(s2, "3.2.S.2.2")
    if s22_text and not _FLOW_CUES.search(s22_text):
        s22_chunks = [c for c in s2 if is_subsection(c, "3.2.S.2.2")]
        findings.append(
            Finding(
                finding_id=make_finding_id(AGENT_ID, case_id, "s22-no-flow"),
                case_id=case_id,
                agent_id=AGENT_ID,
                ctd_section="3.2.S.2.2",
                issue_type="possible_missing_flow_diagram",
                status=FindingStatus.POTENTIAL_GAP,
                sponsor_evidence=[evidence_from_chunk(c) for c in s22_chunks[:2]],
                rationale=(
                    "3.2.S.2.2 is present but no synthetic flow diagram / reaction "
                    "scheme cue was detected in the extracted text. A flow diagram "
                    "of the synthetic process is expected. (Note: diagrams may be "
                    "image-only and not captured as text yet — assessor to confirm.)"
                ),
                uncertainty=0.6,
                attributes={"check": "consistency", "cue": "flow_diagram"},
            )
        )

    # 4. Forward-link risk: starting materials named in S.2 that S.3/S.4
    #    should trace. Emit a link hint for the Cross-Section agent (M4).
    s23_text = _subsection_text(s2, "3.2.S.2.3")
    if s23_text and _STARTING_MATERIAL_CUES.search(s23_text):
        s23_chunks = [
            c for c in s2
            if is_subsection(c, "3.2.S.2.3") and _STARTING_MATERIAL_CUES.search(c.text)
        ]
        findings.append(
            Finding(
                finding_id=make_finding_id(AGENT_ID, case_id, "s23-link"),
                case_id=case_id,
                agent_id=AGENT_ID,
                ctd_section="3.2.S.2.3",
                issue_type="cross_section_link",
                status=FindingStatus.REVIEW_REQUIRED,
                sponsor_evidence=[evidence_from_chunk(c) for c in s23_chunks[:2]],
                rationale=(
                    "Starting materials / reagents / solvents are described in "
                    "3.2.S.2.3. Impurities arising from these should be "
                    "characterised in S.3.2 and controlled in S.4. Flagged for "
                    "cross-section traceability (M4)."
                ),
                uncertainty=0.3,
                attributes={
                    "check": "cross_section",
                    "links_to": ["3.2.S.3.2", "3.2.S.4"],
                },
            )
        )

    return findings
