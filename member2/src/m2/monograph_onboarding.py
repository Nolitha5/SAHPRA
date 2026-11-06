"""Future reviewed pharmacopoeial monographs: intake verification before human release.

Intake DOES NOT grant an approval flag or publish into an authoritative Chroma collection.
Requires the real original PDF and a separate human permissions/edition/adoption review.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
from pydantic import BaseModel, ConfigDict, Field, model_validator

OFFICIAL_HOSTS = {
    "digicollections.net", "www.digicollections.net",
    "www.pharmacopoeia.mhra.gov.uk", "pharmacopoeia.mhra.gov.uk",
    "online.uspnf.com", "www.usp.org", "usp.org",
    "www.edqm.eu", "edqm.eu", "pheur.edqm.eu", "www.pheur.edqm.eu",
    "iponline.ipc.gov.in", "ipc.gov.in", "www.ipc.gov.in",
}


class ReviewedSourceProposal(BaseModel):
    """Fields supplied by the domain/licensing reviewer; cannot verify credentials itself."""
    model_config = ConfigDict(extra="forbid")
    source_id: str = Field(min_length=3, pattern=r"^[A-Za-z0-9_-]+$")
    title: str = Field(min_length=3)
    substance: str = Field(min_length=2)
    cas: str | None = None
    compendium: str = Field(min_length=2)
    edition: str = Field(min_length=2)
    official_source_url: str
    pdf_sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    submission_applicability_date: date | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    license_review_reference: str = Field(min_length=8)
    reviewer_id: str = Field(min_length=2)
    reviewer_basis: str = Field(min_length=12)
    applicable_product_scope: str = Field(min_length=5)
    approval_decision: str = "PENDING_EXTERNAL_CONFIRMATION"

    @model_validator(mode="after")
    def check_evidence_boundary(self):
        u=urlparse(self.official_source_url)
        if u.scheme != "https" or u.hostname not in OFFICIAL_HOSTS or u.username or u.password:
            raise ValueError("Official publisher HTTPS URL required; mirrors are research-discovery only")
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("Invalid edition effective interval")
        if self.approval_decision != "PENDING_EXTERNAL_CONFIRMATION":
            raise ValueError("This staging workflow cannot approve a regulatory source")
        return self


def inspect_candidate(proposal: ReviewedSourceProposal, pdf: Path) -> dict:
    import fitz
    pdf=Path(pdf)
    if not pdf.is_file():
        raise FileNotFoundError(pdf)
    data=pdf.read_bytes()
    if not data.startswith(b"%PDF-"):
        raise ValueError("Expected original valid PDF")
    hash_found=hashlib.sha256(data).hexdigest()
    if hash_found.lower()!=proposal.pdf_sha256.lower():
        raise ValueError("PDF SHA256 does not match reviewed submission")
    with fitz.open(stream=data,filetype="pdf") as doc:
        if doc.page_count == 0:
            raise ValueError("Empty document")
        text="\n".join(doc[i].get_text(sort=True) for i in range(min(doc.page_count,3)))
        pages=doc.page_count
    normal=lambda s:re.sub(r"[^a-z0-9]+", " ", s.casefold()).strip()
    # Identity check of actual content: no title-only PDF/name fabrication.
    identified = normal(proposal.substance) in normal(text)
    if not identified:
        raise ValueError("Expected substance name is absent from PDF opening pages; manual inspection needed")
    return {
        "source_id":proposal.source_id, "sha256_verified":True,
        "identity_in_first_three_pages":True, "pdf_pages":pages,
        "effective_interval_recorded":proposal.effective_from is not None,
        "submission_date_recorded":proposal.submission_applicability_date is not None,
        "edition":proposal.edition, "publisher":urlparse(proposal.official_source_url).hostname,
        "intake_status":"TECHNICALLY_VERIFIED_PENDING_EXTERNAL_REVIEW",
        "publish_to_regulatory_index":False, "expert_validated":False,
        "approval_decision":None,
        "warning":"Hash and identity checks do not prove reviewer authority, reuse rights, edition, or SAHPRA applicability."
    }


def stage_submission(proposal: ReviewedSourceProposal, pdf: Path, out: Path) -> dict:
    result=inspect_candidate(proposal,pdf)
    dest=Path(out)
    dest.mkdir(parents=True,exist_ok=True)
    receipt={"proposal":proposal.model_dump(mode="json"), "checks":result}
    (dest/f"{proposal.source_id}.staged.json").write_text(json.dumps(receipt,indent=2),encoding="utf-8")
    return result
