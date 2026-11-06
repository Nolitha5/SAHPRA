"""Optional LangChain-compatible retrieval adapter. No parallel agent orchestration."""
from __future__ import annotations
import uuid
from .schemas import EvidenceRequest, EvidenceStatus
from .retrieval import EvidenceService

class EvidenceLangChainRetriever:
    """Compatibility facade returning LangChain Documents with provenance metadata.

    The EvidenceService is still the only RKB search implementation. This facade
    does not create or operate its own vector index, and is safe for M1 to swap.
    """
    def __init__(self, service: EvidenceService, requesting_agent: str = "M1", top_k: int = 5):
        self.service=service;self.requesting_agent=requesting_agent;self.top_k=top_k

    def invoke(self, query: str):
        try:
            from langchain_core.documents import Document
        except ImportError as e:
            raise RuntimeError('pip install -e ".[langchain]" for the optional LangChain Document adapter') from e
        result=self.service.retrieve(EvidenceRequest(request_id=str(uuid.uuid4()),question=query,
                    requesting_agent=self.requesting_agent,top_k=self.top_k))
        if result.status != EvidenceStatus.FOUND:
            # Empty document list is intentional; M1 must also inspect EvidenceResult to
            # distinguish no-evidence from infrastructure error before deciding a route.
            return []
        return [Document(page_content=p.passage,metadata={
                    "evidence_id":p.evidence_id,"source_id":p.source_id,"authority":p.authority,
                    "document_code":p.document_code,"section":p.section,"page":p.page,
                    "version":p.version,"citation":p.citation,"retrieval_score_not_calibrated":p.retrieval_score})
                for p in result.evidence]
