"""M1/M5 interface for safe pharmacopoeial lookup. Never returns a regulatory verdict."""
from __future__ import annotations
from datetime import date
from .pharmacopoeia import PharmacopoeiaCatalogue
from .retrieval import EvidenceService
from .schemas import EvidenceRequest, EvidenceFilters, EvidenceStatus


def lookup_compendial_evidence(catalogue: PharmacopoeiaCatalogue, service: EvidenceService,
                               *, substance: str, question: str, requesting_agent: str,
                               cas: str | None = None, as_of: date | None = None) -> dict:
    discovery = catalogue.resolve(substance, cas=cas)
    result = {
        "lookup_status": discovery.status,
        "candidates": discovery.candidates,
        "regulatory_approval_or_rejection": None,
        "human_review_required": True,
        "evidence": [],
        "note": discovery.caution,
    }
    if discovery.status != "REFERENCE_ONLY_REVIEW_REQUIRED":
        return result
    monograph_id = discovery.candidates[0]["id"]
    src = service.registry.records.get(monograph_id)
    if not src or not src.approved or not src.provenance_verified:
        result["lookup_status"] = "MONOGRAPH_REFERENCE_ONLY_NOT_INDEXED_OR_APPROVED"
        return result
    if as_of is not None and src.effective_from is None:
        result["lookup_status"] = "EFFECTIVE_DATE_NOT_VERIFIED"
        return result
    try:
        ev = service.retrieve(EvidenceRequest(
            request_id=f"phint-{monograph_id}",question=question,
            requesting_agent=requesting_agent,
            filters=EvidenceFilters(document_codes=[src.document_code],effective_on=as_of),top_k=5))
    except Exception:
        result["lookup_status"] = "RETRIEVAL_ERROR"
        return result
    result["lookup_status"] = f"RETRIEVAL_{ev.status.value}"
    result["evidence"] = [x.model_dump(mode="json") for x in ev.evidence]
    if ev.status != EvidenceStatus.FOUND:
        result["note"] = ev.reason or result["note"]
    return result
