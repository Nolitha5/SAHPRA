# Member 5 — QA, Interface & Domain

Agentic QA-RAG · SAHPRA Feasibility Study · Branch: `Florah-M5`

This component implements the quality-assurance layer, assessor-facing interface, and
domain ground truth for the SAHPRA Module 3.2.S automated dossier review prototype.

---

## What is built

| Component | Location | Purpose |
|---|---|---|
| **QA/Critic agent** | `backend/qa_critic.py` | Validates each finding structurally; assigns PASS / FLAG / ESCALATE |
| **S.5 Reference Standards agent** | `backend/s5_standards.py` | Checks sponsor pharmacopoeial edition claims against a replaceable monograph repository |
| **Assessor UI (Human Gate)** | `frontend/` | React/Vite/TS interface: findings grouped by CTD section, QA status badges, decision buttons, audit hand-off |
| **M1 adapter stub** | `backend/adapters/m1_adapter.py` | Replaceable interface for M1 Orchestrator `/analyse` and Human Gate callback |
| **M4 audit adapter stub** | `backend/adapters/m4_adapter.py` | Replaceable interface for M4 audit log; writes to `data/audit_log.jsonl` until real contract supplied |
| **Golden-answer fixtures** | `tests/golden/` | Three synthetic dossier scenarios for M4's evaluation harness |

---

## Prerequisites

- Python 3.12+
- Node.js 18+
- pip

---

## Installation

### Backend

```bash
cd backend
pip install -r requirements.txt
```

### Frontend

```bash
cd frontend
npm install
```

---

## Running

### Backend (terminal 1)

```bash
cd backend
uvicorn main:app --reload
```

API available at `http://localhost:8000`.  
Interactive docs at `http://localhost:8000/docs`.

### Frontend (terminal 2)

```bash
cd frontend
npm run dev
```

UI available at `http://localhost:5173`.

> The frontend expects the backend at `http://localhost:8000`.  
> Override by creating `frontend/.env.local` with `VITE_API_URL=http://your-host`.

---

## Testing

```bash
cd backend
python -m pytest tests/ -v
```

**39 tests — 3 files:**

| File | What it covers |
|---|---|
| `tests/test_qa_critic.py` | QA/Critic rules: citation, score range, contradiction, escalation |
| `tests/test_s5_standards.py` | S.5 agent: COMPLIANT, NON_COMPLIANT, NEEDS_REVIEW, replaceability |
| `tests/test_golden_scenarios.py` | Golden-answer scenario validation against QA/Critic output |

---

## API endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `GET` | `/findings` | Raw mock findings (no QA applied) |
| `GET` | `/findings/reviewed` | Mock findings after QA/Critic review (used by UI) |
| `POST` | `/qa/review` | Run QA/Critic on a supplied findings list |
| `POST` | `/s5/check` | Check a sponsor S.5 standard claim |
| `POST` | `/decisions/{finding_id}` | Record assessor decision; writes to stub audit log |
| `POST` | `/m1/human-gate` | Stub: post QA-stamped findings to M1 Human Gate callback |

### Example: check a sponsor S.5 claim

```bash
curl -X POST http://localhost:8000/s5/check \
  -H "Content-Type: application/json" \
  -d '{
    "substance_name": "Ethanol",
    "standard": "BP",
    "edition_claimed": "BP 2019",
    "submission_date": "2024-03-01"
  }'
```

### Example: run QA review

```bash
curl -X POST http://localhost:8000/qa/review \
  -H "Content-Type: application/json" \
  -d '{"findings": [...]}'
```

---

## Mock data

| File | Contents |
|---|---|
| `backend/mock_findings.json` | 5 synthetic findings across 3 CTD sections |
| `backend/s5_standards.py` (`_MOCK_RECORDS`) | BP Ethanol (2019, 2020, 2024) and USP Aspirin (42, 47) |
| `tests/golden/scenario_pass.json` | 3 structurally valid findings — all PASS |
| `tests/golden/scenario_identity_fail.json` | CAS number mismatch (Ethanol vs Formaldehyde) |
| `tests/golden/scenario_outdated_standard.json` | BP 2019 claimed at 2024 submission date |

All mock data is synthetic and clearly labelled. No real dossier data is used.

---

## QA/Critic — PASS vs FLAG

`PASS` means the finding is **structurally sound and ready for assessor review**.  
It does NOT mean the substance is compliant.

| Status | Meaning |
|---|---|
| `PASS` | Citation present · score in [0,100] · rationale consistent with evidence |
| `FLAG` | One or more structural rules violated |
| `ESCALATE` | Two or more findings in the same CTD section are FLAG |

The assessor sees all findings regardless of QA status. No finding is suppressed.

---

## Golden-answer files (for M4)

**Location agreed:** `tests/golden/`

Each file follows this schema:

```json
{
  "_meta":    { "scenario", "description", "version", "author" },
  "input":    { "findings": [...] },
  "expected_output": {
    "findings": [{ "finding_id", "qa_status" }],
    "section_escalations": []
  }
}
```

M4's harness should:
1. Load `input.findings` into the QA/Critic.
2. Compare each result's `qa_status` to `expected_output.findings[*].qa_status`.

---

## Contracts still required from team members

### M1 — Orchestrator

- Request schema for `/analyse` (what identifies a dossier?)
- Response schema — does M1 return findings in the `Finding` shape defined in `models.py`?
- Human Gate callback URL and expected payload
- Authentication mechanism

**Stub location:** `backend/adapters/m1_adapter.py` · class `MockM1Adapter`

### M2 — Retrieval / RKB

- How to query for a pharmacopoeial monograph by standard + substance + date
- Response schema — fields for monograph name, edition, page, valid-from date
- Whether the RKB exposes an HTTP API or a Python function

**Stub location:** `backend/s5_standards.py` · class `MockMonographRepository`  
**Interface to implement:** `MonographRepository` Protocol in the same file

### M3 — Ingestion

- Format of the structured S.5 section JSON (sponsor claims)
- Does it match the `S5Claim` schema in `models.py`?

### M4 — Memory / Evaluation

- Audit log endpoint URL (or confirm `tests/golden/` file path)
- Audit record schema — which fields are required
- Confirmation mechanism

**Stub location:** `backend/adapters/m4_adapter.py` · class `LocalFileAuditAdapter`  
**Interface to implement:** `M4AuditAdapter` Protocol in the same file

---

## Files M4 needs

| File | Purpose |
|---|---|
| `tests/golden/scenario_pass.json` | All-PASS baseline scenario |
| `tests/golden/scenario_identity_fail.json` | CAS mismatch scenario |
| `tests/golden/scenario_outdated_standard.json` | Outdated pharmacopoeial edition scenario |
| `backend/models.py` | `Finding` schema (Pydantic v2) |

---

## Regulatory note

All AI findings are assistance for a human assessor.  
No finding constitutes autonomous approval or rejection of a medicine.  
Every FLAG is visible to the assessor; none are suppressed.
