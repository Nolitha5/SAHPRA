import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from adapters.m1_adapter import MockM1Adapter
from adapters.m4_adapter import LocalFileAuditAdapter, make_audit_record
from models import AssessorDecisionRequest, Finding, S5Claim, S5Finding
from qa_critic import review_findings
from s5_standards import MockMonographRepository, check_s5_claim

app = FastAPI(title="SAHPRA M5 API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_methods=["*"],
    allow_headers=["*"],
)

# Adapter instances — swap these for real implementations once contracts are supplied
_m1 = MockM1Adapter()
_m4 = LocalFileAuditAdapter()
_monograph_repo = MockMonographRepository()

_FIXTURES = Path(__file__).parent / "mock_findings.json"


def _load_raw_findings() -> list[Finding]:
    data = json.loads(_FIXTURES.read_text(encoding="utf-8"))
    return [Finding(**item) for item in data]


# ── Health ────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


# ── Findings ──────────────────────────────────────────────────────────

@app.get("/findings", response_model=list[Finding])
def get_findings():
    """Raw mock findings — no QA review applied."""
    return _load_raw_findings()


@app.get("/findings/reviewed", response_model=list[Finding])
def get_reviewed_findings():
    """
    Mock findings after QA/Critic review.
    In production this is replaced by findings returned from M1's /analyse endpoint.
    """
    return _m1.get_findings(dossier_id="mock")


@app.get("/findings/{finding_id}", response_model=Finding)
def get_finding(finding_id: str):
    findings = {f.finding_id: f for f in _load_raw_findings()}
    if finding_id not in findings:
        raise HTTPException(status_code=404, detail="Finding not found")
    return findings[finding_id]


# ── QA / Critic ───────────────────────────────────────────────────────

from pydantic import BaseModel  # noqa: E402 — kept at use site for clarity


class FindingsListRequest(BaseModel):
    findings: list[Finding]


@app.post("/qa/review", response_model=list[Finding])
def qa_review(body: FindingsListRequest):
    """
    Run the QA/Critic over a supplied list of findings.
    Returns the same findings with qa_status set on each.
    No findings are removed.
    """
    return review_findings(body.findings)


# ── S.5 Reference Standards ───────────────────────────────────────────

@app.post("/s5/check", response_model=S5Finding)
def s5_check(claim: S5Claim):
    """
    Check a sponsor's S.5 pharmacopoeial standard claim.
    Returns COMPLIANT, NON_COMPLIANT, or NEEDS_REVIEW — never an invented verdict.
    """
    return check_s5_claim(claim, _monograph_repo)


# ── Assessor decisions ────────────────────────────────────────────────

class DecisionResponse(BaseModel):
    finding_id: str
    decision: str
    timestamp: str
    audit_stub: bool
    audit_saved: bool
    message: str


@app.post("/decisions/{finding_id}", response_model=DecisionResponse)
def record_decision(finding_id: str, body: AssessorDecisionRequest):
    """
    Record an assessor decision for a finding.

    The decision is written to the local stub audit log (data/audit_log.jsonl).
    audit_stub=True and audit_saved reflects whether the write succeeded.
    This does NOT confirm that M4's real audit service has received the record.
    Replace _m4 with a real M4AuditAdapter once the contract is supplied.
    """
    if body.finding_id != finding_id:
        raise HTTPException(
            status_code=422,
            detail="finding_id in path and body must match",
        )

    record = make_audit_record(
        finding_id=finding_id,
        decision=body.decision,
        disposition_note=body.disposition_note,
    )
    saved = _m4.record_decision(record)

    return DecisionResponse(
        finding_id=finding_id,
        decision=body.decision,
        timestamp=record.timestamp,
        audit_stub=True,
        audit_saved=saved,
        message=(
            "Decision written to local stub audit log."
            if saved
            else "Decision processed but stub audit write failed."
        ),
    )


# ── M1 Human Gate callback ────────────────────────────────────────────

class HumanGateRequest(BaseModel):
    dossier_id: str
    findings: list[Finding]


class HumanGateResponse(BaseModel):
    dossier_id: str
    acknowledged: bool
    stub: bool
    message: str


@app.post("/m1/human-gate", response_model=HumanGateResponse)
def post_human_gate(body: HumanGateRequest):
    """
    Post QA-stamped findings and assessor decisions to M1's Human Gate.
    Currently a stub — replace _m1 with a real adapter once M1 supplies the contract.
    """
    ok = _m1.post_human_gate_result(
        dossier_id=body.dossier_id,
        findings=body.findings,
    )
    return HumanGateResponse(
        dossier_id=body.dossier_id,
        acknowledged=ok,
        stub=True,
        message="Stub: M1 Human Gate contract not yet supplied.",
    )
