"""Member 1 LangGraph integration adapters. No direct inter-agent invocation."""
from .runtime import M2Runtime
from .schemas import EvidenceRequest, S4ReviewRequest

def evidence_node(runtime: M2Runtime):
    """LangGraph-compatible function returning a state patch, not mutating case memory."""
    def node(state: dict) -> dict:
        req = EvidenceRequest.model_validate(state["evidence_request"])
        return {"evidence_result": runtime.evidence.retrieve(req).model_dump(mode="json")}
    return node

def s4_node(runtime: M2Runtime):
    def node(state: dict) -> dict:
        req = S4ReviewRequest.model_validate(state["s4_request"])
        review = runtime.s4.review(req)
        return {"s4_result": review.model_dump(mode="json"),
                "findings": [f.model_dump(mode="json") for f in review.findings]}
    return node
