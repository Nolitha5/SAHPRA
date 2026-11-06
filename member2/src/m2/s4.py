"""S.4 Control: cautious, cited, provisional observations; no autonomous compliance verdict."""
import hashlib
import re
from .schemas import (S4ReviewRequest,S4ReviewResult,Finding,FindingStatus,QAStatus,
                      EvidenceRequest,EvidenceFilters,EvidenceStatus,SponsorEvidence,DossierChunk)
from .retrieval import EvidenceService
from .ollama import OllamaClient
from .s4_rules import compare_sponsor_batch_data

S4_TOPICS = {
    "3.2.S.4.1": ("Specification", "drug substance specifications tests acceptance criteria limits"),
    "3.2.S.4.2": ("Analytical Procedures", "drug substance analytical test procedures methods"),
    "3.2.S.4.3": ("Validation of Analytical Procedures", "drug substance analytical procedures method validation"),
    "3.2.S.4.4": ("Batch Analyses", "drug substance batch analyses results specifications"),
    "3.2.S.4.5": ("Justification of Specification", "drug substance specifications acceptance criteria justification"),
}

class S4ControlAgent:
    def __init__(self, evidence: EvidenceService, llm: OllamaClient | None = None):
        self.evidence,self.llm = evidence,llm

    @staticmethod
    def extract_s4_fields(chunks: list[DossierChunk]) -> dict:
        """Deterministic, provenance-preserving extraction hints, NOT validated chemical interpretation."""
        terms = {"specifications":r"\bspecification(?:s)?\b|\bacceptance\s+criteria\b",
                 "limits":r"\blimit(?:s)?\b|[<>≤≥]\s*\d+(?:\.\d+)?\s*(?:%|ppm|mg)",
                 "analytical_methods":r"\b(?:hplc|gc|uv|lc-ms|analytical method|analytical procedure)\b",
                 "validation":r"\b(?:validation|accuracy|precision|linearity|specificity|robustness)\b",
                 "batch_analyses":r"\b(?:batch|batch analysis|coa|certificate of analysis)\b"}
        output = {name:[] for name in terms}
        for c in chunks:
            if not c.ctd_section.upper().startswith("3.2.S.4"):continue
            for name, regex in terms.items():
                if re.search(regex, c.text, re.IGNORECASE):
                    output[name].append({"chunk_id":c.chunk_id,"document_id":c.document_id,"ctd_section":c.ctd_section})
        return output

    def review(self, req: S4ReviewRequest) -> S4ReviewResult:
        valid_chunks = [c for c in req.dossier_chunks if c.ctd_section.upper().startswith("3.2.S.4") and not c.quality_flag]
        fields = self.extract_s4_fields(valid_chunks)
        findings: list[Finding] = []
        for section, (label, question) in S4_TOPICS.items():
            chunks = [c for c in valid_chunks if c.ctd_section.upper().startswith(section)]
            evidence = self.evidence.retrieve(EvidenceRequest(
                request_id=f"{req.case_id}:{section}",question=question,
                requesting_agent="S4_CONTROL",case_id=req.case_id,
                filters=EvidenceFilters(document_codes=req.relevant_regulatory_codes,effective_on=req.as_of),top_k=4))
            sponsor = [SponsorEvidence(document_id=c.document_id,chunk_id=c.chunk_id,
                       ctd_section=c.ctd_section,passage=c.text[:1500],page=c.page) for c in chunks[:8]]
            if not chunks:
                status=FindingStatus.MISSING_INFORMATION
                rationale=f"No extractable sponsor content tagged {section} ({label}) was supplied to S.4. Verify dossier completeness and M3 extraction before interpreting this as a deficiency."
            elif evidence.status != EvidenceStatus.FOUND:
                status=FindingStatus.INSUFFICIENT_EVIDENCE
                rationale=f"Sponsor content for {section} was provided, but applicable regulatory evidence was not established ({evidence.status.value}). Human source verification is required."
            else:
                status=FindingStatus.REVIEW_REQUIRED
                rationale=f"Sponsor content under {section} ({label}) is available for expert comparison with the cited regulatory passages; no automated approval or non-compliance conclusion is asserted."
            finding_id = "s4-"+hashlib.sha256((req.case_id+":"+section).encode()).hexdigest()[:18]
            finding = Finding(finding_id=finding_id,case_id=req.case_id,agent_id="S4_CONTROL",
                ctd_section=section, issue_type=label, status=status, sponsor_evidence=sponsor,
                regulatory_evidence=evidence.evidence, rationale=rationale,
                uncertainty=0.9 if (not chunks or evidence.status!=EvidenceStatus.FOUND) else 0.65,
                qa_status=QAStatus.PENDING,requires_human_review=True,
                attributes={"extractor": "keyword-hints-v1", "extraction_hints": {k:v for k,v in fields.items() if v},
                            "evidence_status":evidence.status.value})
            if self.llm and chunks and evidence.status == EvidenceStatus.FOUND:
                self._optional_llm_gap_analysis(finding)
            findings.append(finding)
        # Structured numeric cross-checks use sponsor-supplied values, never invented regulatory thresholds.
        for idx, observation in enumerate(compare_sponsor_batch_data(valid_chunks)):
            evidence = self.evidence.retrieve(EvidenceRequest(request_id=f"{req.case_id}:num:{idx}",
                question="drug substance batch analyses results specifications acceptance criteria limits",
                requesting_agent="S4_CONTROL",case_id=req.case_id,
                filters=EvidenceFilters(document_codes=req.relevant_regulatory_codes,effective_on=req.as_of),top_k=3))
            relevant = [c for c in valid_chunks if c.chunk_id in observation.source_chunk_ids]
            findings.append(Finding(
                finding_id="s4-num-"+hashlib.sha256((req.case_id+str(idx)+observation.test_name).encode()).hexdigest()[:18],
                case_id=req.case_id,agent_id="S4_CONTROL",ctd_section="3.2.S.4.4",
                issue_type=observation.issue_type,status=FindingStatus.POTENTIAL_GAP,
                sponsor_evidence=[SponsorEvidence(document_id=c.document_id,chunk_id=c.chunk_id,
                    ctd_section=c.ctd_section,passage=c.text[:1500],page=c.page) for c in relevant],
                regulatory_evidence=evidence.evidence,rationale=observation.description,
                uncertainty=0.35 if evidence.status==EvidenceStatus.FOUND else 0.7,
                qa_status=QAStatus.PENDING,requires_human_review=True,
                attributes={"candidate_numeric_discrepancy":observation.data,"no_regulatory_verdict":True,
                    "regulatory_evidence_status":evidence.status.value}))
        return S4ReviewResult(case_id=req.case_id,findings=findings)

    def _optional_llm_gap_analysis(self, finding: Finding):
        # Only accept quote anchored in provided sponsor evidence and evidence IDs already retrieved.
        sponsor_text = "\n".join(p.passage for p in finding.sponsor_evidence)[:6000]
        regulatory = "\n".join(f"{p.evidence_id}: {p.passage}" for p in finding.regulatory_evidence)[:6000]
        prompt = ("You are assisting, not deciding, a regulatory drug-substance review. Do not infer missing "
            "regulatory requirements or final compliance. Return JSON with keys observation, "
            "sponsor_quote, evidence_id, potential_gap (boolean). The sponsor_quote must be copied "
            "exactly from sponsor text. If uncertain, set potential_gap false and sponsor_quote ''.\n"
            f"SPONSOR TEXT:\n{sponsor_text}\nREGULATORY EVIDENCE:\n{regulatory}")
        try:
            data = self.llm.json_completion(prompt)
            quote = str(data.get("sponsor_quote", ""))
            ev_id = str(data.get("evidence_id", ""))
            if not quote or quote not in sponsor_text or ev_id not in {p.evidence_id for p in finding.regulatory_evidence}:
                return
            observation = str(data.get("observation", ""))[:600]
            if not observation: return
            finding.attributes["llm_observation_unverified"] = observation
            finding.attributes["llm_quote"] = quote
            finding.attributes["llm_evidence_id"] = ev_id
            if data.get("potential_gap") is True:
                finding.status = FindingStatus.POTENTIAL_GAP
                finding.rationale += " A model flagged a potential gap; the assessor and QA/Critic must independently verify this observation."
        except Exception as e:
            finding.attributes["llm_error_class"] = type(e).__name__
