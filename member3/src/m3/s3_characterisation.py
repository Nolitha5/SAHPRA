"""
S.3 Characterisation agent.

Assesses structure-elucidation evidence and impurity characterisation in
3.2.S.3, per IPRP QWGG guidance / ICH Q6A, M7, Q3A:

  S.3.1  Elucidation of Structure and other Characteristics
  S.3.2  Impurities

Two jobs:
  1. Completeness/consistency of the characterisation evidence (were the
     expected techniques — IR, UV, NMR, MS, elemental analysis, XRD —
     referenced for a non-compendial substance?).
  2. Impurity linking: extract impurities named in S.3.2 and flag that each
     should be controlled in S.4 and, where process-related, traced back to
     S.2 (the "made in S.2 -> characterised in S.3 -> controlled in S.4 ->
     tracked in S.7" chain). These become cross-section hints for M4.

No regulatory judgement is made here; findings are for the human assessor.
"""
from __future__ import annotations

import re

from .agents_common import (
    chunks_in_section,
    evidence_from_chunk,
    make_finding_id,
    missing_subsection_finding,
    present_subsections,
)
from .schemas import DossierChunk, Finding, FindingStatus

AGENT_ID = "S3_CHARACTERISATION"

_REQUIRED_SUBSECTIONS = {
    "3.2.S.3.1": "Elucidation of Structure and other Characteristics",
    "3.2.S.3.2": "Impurities",
}

# Structure-elucidation techniques expected for a non-compendial substance.
_TECHNIQUES = {
    "IR": re.compile(r"\b(IR|infra[- ]?red|FTIR)\b", re.I),
    "UV": re.compile(r"\b(UV|ultra[- ]?violet)\b", re.I),
    "NMR": re.compile(r"\b(NMR|nuclear magnetic)\b", re.I),
    "MS": re.compile(r"\b(mass spec|MS|m/z)\b", re.I),
    "elemental": re.compile(r"\belemental analysis\b", re.I),
    "XRD": re.compile(r"\b(XRD|x[- ]?ray diffraction)\b", re.I),
}

# Impurity mention + an associated level like "0.08%" or "0.1 %".
_IMPURITY_RE = re.compile(
    r"\b(impurity|impurities|degradation product|related substance)\b",
    re.I,
)
_IMPURITY_NAMED_RE = re.compile(
    r"\bimpurity\s+([A-Z0-9][\w\-]*)\b",
    re.I,
)
_LEVEL_RE = re.compile(r"\b\d+(?:\.\d+)?\s?%")


def _subsection_text(chunks: list[DossierChunk], code: str) -> str:
    return " ".join(c.text for c in chunks if c.ctd_section.upper() == code.upper())


def review(case_id: str, chunks: list[DossierChunk]) -> list[Finding]:
    s3 = chunks_in_section(chunks, "3.2.S.3")
    findings: list[Finding] = []

    if not s3:
        findings.append(
            Finding(
                finding_id=make_finding_id(AGENT_ID, case_id, "no-s3"),
                case_id=case_id,
                agent_id=AGENT_ID,
                ctd_section="3.2.S.3",
                issue_type="section_absent",
                status=FindingStatus.MISSING_INFORMATION,
                rationale=(
                    "No content was attributed to section 3.2.S.3 "
                    "(Characterisation) during ingestion. Assessor must confirm."
                ),
                uncertainty=0.6,
                attributes={"check": "completeness"},
            )
        )
        return findings

    present = present_subsections(s3)
    sibling_evidence = [evidence_from_chunk(c) for c in s3[:2]]

    # 1. Completeness
    for code, title in _REQUIRED_SUBSECTIONS.items():
        if code not in present:
            findings.append(
                missing_subsection_finding(AGENT_ID, case_id, code, title, sibling_evidence)
            )

    # 2. Structure-elucidation techniques present in S.3.1?
    s31_text = _subsection_text(s3, "3.2.S.3.1")
    if s31_text:
        found = [name for name, rx in _TECHNIQUES.items() if rx.search(s31_text)]
        if len(found) < 2:
            s31_chunks = [c for c in s3 if c.ctd_section.upper() == "3.2.S.3.1"]
            findings.append(
                Finding(
                    finding_id=make_finding_id(AGENT_ID, case_id, "s31-techniques"),
                    case_id=case_id,
                    agent_id=AGENT_ID,
                    ctd_section="3.2.S.3.1",
                    issue_type="limited_structure_evidence",
                    status=FindingStatus.POTENTIAL_GAP,
                    sponsor_evidence=[evidence_from_chunk(c) for c in s31_chunks[:2]],
                    rationale=(
                        "Few structure-elucidation techniques were detected in "
                        f"3.2.S.3.1 (found: {found or 'none'}). For a non-compendial "
                        "substance, elemental analysis, IR, UV, NMR and MS are "
                        "normally expected. Assessor to confirm sufficiency "
                        "(spectra may be image-only and not yet captured as text)."
                    ),
                    uncertainty=0.55,
                    attributes={"check": "consistency", "techniques_found": found},
                )
            )

    # 3. Impurities named in S.3.2 -> link to S.4 control.
    s32_chunks = [c for c in s3 if c.ctd_section.upper() == "3.2.S.3.2"]
    s32_text = _subsection_text(s3, "3.2.S.3.2")
    if s32_text and _IMPURITY_RE.search(s32_text):
        named = sorted({m.group(1).upper() for m in _IMPURITY_NAMED_RE.finditer(s32_text)})
        has_levels = bool(_LEVEL_RE.search(s32_text))
        findings.append(
            Finding(
                finding_id=make_finding_id(AGENT_ID, case_id, "s32-impurity-link"),
                case_id=case_id,
                agent_id=AGENT_ID,
                ctd_section="3.2.S.3.2",
                issue_type="impurity_cross_section_link",
                status=FindingStatus.REVIEW_REQUIRED,
                sponsor_evidence=[evidence_from_chunk(c) for c in s32_chunks[:3]],
                rationale=(
                    "Impurities are described in 3.2.S.3.2"
                    + (f" (named: {', '.join(named)})" if named else "")
                    + ". Each identified impurity should have a corresponding "
                    "acceptance criterion in S.4.1 and, where process-related, be "
                    "traceable to starting materials in S.2.3. Flagged for "
                    "cross-section traceability (M4) and S.4 control (M2)."
                ),
                uncertainty=0.35,
                attributes={
                    "check": "cross_section",
                    "named_impurities": named,
                    "levels_detected": has_levels,
                    "links_to": ["3.2.S.4.1", "3.2.S.2.3", "3.2.S.7.3"],
                },
            )
        )

    return findings
