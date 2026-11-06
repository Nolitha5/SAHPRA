"""Optional REST mount for M1; main production app, auth and audit belong to M1/M4."""
from __future__ import annotations
import os
import secrets
from fastapi import FastAPI, APIRouter, Depends, HTTPException, Header
from .runtime import AppConfig, M2Runtime
from .schemas import EvidenceRequest,EvidenceResult,S4ReviewRequest,S4ReviewResult
from .pharmacopoeia import PharmacopoeiaCatalogue
from .pharmacopoeia_service import lookup_compendial_evidence
from pydantic import BaseModel, Field
from datetime import date
from pathlib import Path

_current_runtime: M2Runtime | None = None

def set_runtime(runtime: M2Runtime):
    global _current_runtime
    _current_runtime = runtime

def get_runtime() -> M2Runtime:
    if _current_runtime is None:
        raise HTTPException(status_code=503,detail="Member 2 runtime is not configured")
    return _current_runtime

def require_auth(x_m2_token: str | None = Header(default=None), runtime: M2Runtime = Depends(get_runtime)):
    if runtime.cfg.mode == "research":
        configured=os.environ.get("M2_SERVICE_TOKEN")
        if not configured:
            raise HTTPException(status_code=503,detail="Set M2_SERVICE_TOKEN before exposing research service")
        if not x_m2_token or not secrets.compare_digest(x_m2_token,configured):
            raise HTTPException(status_code=401,detail="Invalid Member 2 service credential")

router=APIRouter(prefix="/m2",tags=["Member 2 Retrieval & S.4"],dependencies=[Depends(require_auth)])

@router.get("/health")
def health(runtime: M2Runtime=Depends(get_runtime)):
    return {"service":"M2",**runtime.stats()}

@router.post("/evidence",response_model=EvidenceResult)
def evidence(req: EvidenceRequest,runtime: M2Runtime=Depends(get_runtime)):
    return runtime.evidence.retrieve(req)

@router.post("/s4/review",response_model=S4ReviewResult)
def review_s4(req:S4ReviewRequest,runtime:M2Runtime=Depends(get_runtime)):
    return runtime.s4.review(req)

class PhIntLookupRequest(BaseModel):
    substance: str = Field(min_length=1)
    cas: str | None = None
    question: str = Field(min_length=3)
    requesting_agent: str = "S4_CONTROL"
    as_of: date | None = None

@router.post("/phint/evidence")
def phint_evidence(req: PhIntLookupRequest, runtime: M2Runtime=Depends(get_runtime)):
    """Metadata-only discovery unless a separately reviewed monograph is indexed."""
    catalog_path=os.environ.get("M2_PHINT_CATALOGUE")
    if not catalog_path:
        raise HTTPException(status_code=503,detail="M2_PHINT_CATALOGUE must point to the research catalogue")
    catalogue=PharmacopoeiaCatalogue.load(Path(catalog_path))
    return lookup_compendial_evidence(catalogue,runtime.evidence,
        substance=req.substance,cas=req.cas,question=req.question,
        requesting_agent=req.requesting_agent,as_of=req.as_of)

# Provisional interface for M1 orchestration / M5 S.5 while reviewed monographs are deferred.
# Research leads are disabled by default and are NEVER returned as regulatory evidence.
from .deferred_handoff import SponsorClaim, build_handoff

@router.post("/compendia/deferred-assessment")
def deferred_assessment(req: SponsorClaim, runtime: M2Runtime = Depends(get_runtime)):
    catalogue_path = os.environ.get("M2_PHINT_CATALOGUE")
    if not catalogue_path:
        raise HTTPException(status_code=503, detail="M2_PHINT_CATALOGUE must be configured")
    catalogue = PharmacopoeiaCatalogue.load(Path(catalogue_path))
    return build_handoff(req, catalogue)

app=FastAPI(title="Member 2 standalone development service",version="0.1.0")
app.include_router(router)
# No automatic external-model downloads or index writes on import.
# Optional startup configuration is explicitly opt-in, because importing this
# router into M1 must not unexpectedly read data or start its own persistence.
if os.environ.get("M2_STARTUP_CONFIG"):
    set_runtime(M2Runtime(AppConfig.from_file(os.environ["M2_STARTUP_CONFIG"])))
