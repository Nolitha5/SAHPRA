"""Provisional Member-2 -> M1/M4/M5 handoff while compendial content awaits review.

No unverified compendial reference, missing edition, or navigation preview can
be promoted to regulatory evidence or an autonomous drug approval by this API.
The returned checklist is derived from the nonbinding IPRP QWGG guidance.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Literal
import json

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .assessor_checklist import prompts
from .compendia_ingest import search_unverified
from .pharmacopoeia import PharmacopoeiaCatalogue, norm


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SponsorClaim(Strict):
    case_id: str = Field(min_length=2)
    drug_substance: str = Field(min_length=2)
    cas: str | None = None
    product_type: Literal["CHEMICAL", "BIOLOGICAL", "UNKNOWN"] = "UNKNOWN"
    claimed_compendium: str | None = None
    claimed_edition: str | None = None
    submission_date: date | None = None
    s4_fields: dict[str, dict[str, Any]] = Field(default_factory=dict)
    s5_fields: dict[str, Any] = Field(default_factory=dict)
    sponsor_document_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def safe_sections(self):
        bad = [s for s in self.s4_fields if s not in {
            "3.2.S.4.1", "3.2.S.4.2", "3.2.S.4.3", "3.2.S.4.4", "3.2.S.4.5"}]
        if bad:
            raise ValueError(f"Unexpected S.4 sections: {bad}")
        return self


S4_SECTIONS = ("3.2.S.4.1", "3.2.S.4.2", "3.2.S.4.3", "3.2.S.4.4", "3.2.S.4.5")


def build_handoff(
    claim: SponsorClaim,
    catalogue: PharmacopoeiaCatalogue,
    *,
    research_index: Path | None = None,
    include_unreviewed_candidates: bool = False,
) -> dict[str, Any]:
    """Create meaningful technical handoff with zero unverified regulatory citations.

    ``research_index`` is only for optional lead discovery; its preview text is
    *not* forwarded to the QA/Critic or treated as accepted regulatory evidence.
    """
    match = catalogue.resolve(claim.drug_substance, cas=claim.cas)
    questions = {section: prompts(section, extracted_sponsor_fields=claim.s4_fields.get(section))
                 for section in S4_SECTIONS}
    s5 = prompts("3.2.S.5", extracted_sponsor_fields=claim.s5_fields)
    blockers = []
    if not claim.claimed_compendium:
        blockers.append("Sponsor's claimed pharmacopoeia has not been supplied or verified")
    if not claim.claimed_edition:
        blockers.append("Sponsor's claimed pharmacopoeial edition has not been supplied or verified")
    if claim.submission_date is None:
        blockers.append("Submission date absent; historical edition applicability cannot be checked")
    if claim.product_type == "UNKNOWN":
        blockers.append("Substance type not specified; chemical/biological guideline scope needs review")
    if claim.product_type == "BIOLOGICAL":
        blockers.append("The IPRP QWGG assessor guidance is chemical-substance specific; do not apply automatically")
    if match.status == "IDENTIFIER_CONFLICT":
        blockers.append("Sponsor name and CAS conflict with WHO reference catalogue; identity check required")
    elif match.status == "AMBIGUOUS":
        blockers.append("More than one WHO catalogue candidate; domain selection required")
    elif match.status not in {"REFERENCE_ONLY_REVIEW_REQUIRED"}:
        blockers.append("No unambiguous WHO monograph catalogue match")
    else:
        blockers.append("WHO monograph is a reference-only catalogue entry; content/edition not approved")
    # Candidate research citations must be labelled and must not expose regulatory passage text.
    research_leads: list[dict[str, Any]] = []
    if research_index is not None and include_unreviewed_candidates:
        result = search_unverified(Path(research_index), claim.drug_substance, limit=15,
                                   topic="SUBSTANCE_MONOGRAPH", include_unreviewed=True, exact_title=True)
        for hit in result.get("hits", []):
            research_leads.append({
                "title": hit["title"], "source_family": hit["source_family"],
                "edition_claim_unverified": hit["edition_claim"],
                "archive_name": hit["archive_name"],
                "path_in_archive": hit["path_in_archive"],
                "review_status": hit["review_status"],
                "regulatory_evidence": False,
            })
    # The task is to *support* M5, not to pre-authorize/reject applicant submissions.
    return {
        "schema_version": "m2-deferred-compendial-handoff-v1",
        "case_id": claim.case_id,
        "substance": claim.drug_substance,
        "cas": claim.cas,
        "product_type": claim.product_type,
        "submission_date": claim.submission_date.isoformat() if claim.submission_date else None,
        "claimed_compendium": claim.claimed_compendium,
        "claimed_edition": claim.claimed_edition,
        "who_catalogue": {
            "status": match.status,
            "candidate_metadata_only": match.candidates,
            "has_approved_monograph_evidence": False,
        },
        "research_only_leads": research_leads,
        "s4_nonbinding_review_checklists": questions,
        "s5_nonbinding_review_checklist": s5,
        "cross_member_issues": blockers,
        "m1_orchestrator_next": "ROUTE_S4_AND_S5_TO_HUMAN_REVIEW_AND_M5_QA",
        "m4_audit_event": "COMPENDIAL_EVIDENCE_PENDING_EXTERNAL_REVIEW",
        "m5_requested_actions": [
            "Verify substance identity, CAS and claimed compendium against sponsor evidence",
            "Obtain the applicable licensed/authorised monograph and verify edition effective at submission",
            "Confirm monograph/source relevance and reference-standard qualification",
            "Label acceptable evidence for S.4/S.5 and independently sign off findings",
        ],
        "regulatory_evidence": [],
        "expert_reviewed": False,
        "qa_status": "PENDING",
        "autonomous_compliance_verdict": None,
        "drug_authorisation_decision": None,
        "requires_human_review": True,
        "warning": "Research-only dossier triage; unreviewed pharmacopoeial extracts never support a regulatory conclusion.",
    }


def dataset_readiness(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Engineering flow coverage without pretending the cases have expert gold."""
    count = len(records)
    return {
        "case_count": count,
        "qa_pending": sum(x["qa_status"] == "PENDING" for x in records),
        "human_review_required": sum(x["requires_human_review"] is True for x in records),
        "no_autonomous_verdict": all(x["drug_authorisation_decision"] is None and
                                     x["autonomous_compliance_verdict"] is None for x in records),
        "unverified_research_leads": sum(len(x["research_only_leads"]) for x in records),
        "technical_handoff_status": "PASS" if records and all(
            x["requires_human_review"] and not x["regulatory_evidence"] for x in records) else "INCOMPLETE",
        "evaluation_type": "ENGINEERING_CONTRACT_CHECK_ONLY",
        "retrieval_precision_at_k": None,
        "s4_s5_regulatory_accuracy": None,
        "expert_validated": False,
    }


def load_cases(path: str | Path) -> list[SponsorClaim]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("label_status") != "SYNTHETIC_ENGINEERING_FIXTURES":
        raise ValueError("Only explicitly labelled synthetic engineering fixtures supported by this demo")
    cases = [SponsorClaim.model_validate(v) for v in data["cases"]]
    if len({c.case_id for c in cases}) != len(cases):
        raise ValueError("Duplicate case IDs")
    return cases
