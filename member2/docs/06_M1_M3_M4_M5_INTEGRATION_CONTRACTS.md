# M1–M5 Integration Contracts
**Version:** 1.2 | **Date:** 2026-10-28  
**Status:** Provisional — pending M1 ratification

---

## 1. Member Architecture

| Member | Role |
|--------|------|
| M1 | Orchestration, runtime integration, S.1 Identity |
| M2 | Evidence/RERA, Regulatory Knowledge Base, S.4 Control |
| M3 | Ingestion/OCR, S.2 Manufacture, S.3 Characterisation |
| M4 | Memory, consistency evaluation, S.6 and S.7 |
| M5 | QA/Critic, S.5 Reference Standards, expert-labelled evaluation |

---

## 2. M1 → M2 Contracts

### 2.1 Evidence Retrieval

**Request:** `EvidenceRequest` (`schemas.py`)
```python
{
  "request_id": str,         # Unique per call
  "question": str,           # Natural language query (min 3 chars)
  "requesting_agent": str,   # e.g. "M1_ORCHESTRATOR"
  "case_id": str | None,
  "filters": {
    "authorities": [...],
    "document_codes": [...],
    "sections": [...],
    "effective_on": "YYYY-MM-DD" | None,
    "include_literature": false
  },
  "top_k": 5                 # 1–100
}
```

**Response:** `EvidenceResult` (`schemas.py`)
```python
{
  "request_id": str,
  "status": "FOUND" | "INSUFFICIENT_EVIDENCE" | "ERROR",
  "evidence": [EvidencePassage, ...],  # Empty if not FOUND
  "requires_human_review": bool,
  "reason": str | None
}
```

**REST:** `POST /m2/evidence`  
**LangGraph:** `integration.evidence_node(runtime)(state)`

### 2.2 S.4 Control Review

**Request:** `S4ReviewRequest`
```python
{
  "case_id": str,
  "dossier_chunks": [DossierChunk, ...],
  "as_of": "YYYY-MM-DD" | None,
  "relevant_regulatory_codes": [...]
}
```

**Response:** `S4ReviewResult`
```python
{
  "case_id": str,
  "agent_id": "S4_CONTROL",
  "findings": [Finding, ...],
  "status": "REVIEW_REQUIRED"
}
```

**REST:** `POST /m2/s4/review`  
**LangGraph:** `integration.s4_node(runtime)(state)`

---

## 3. M3 → M2 Contract

M3 produces `DossierChunk` objects extracted from sponsor dossier PDFs.
These are passed as `S4ReviewRequest.dossier_chunks`.

```python
class DossierChunk:
    chunk_id: str        # Stable ID from M3 extraction
    document_id: str     # Sponsor document identifier
    ctd_section: str     # e.g. "3.2.S.4.1"
    text: str            # Extracted text
    page: int | None
    kind: str            # "text", "table", etc.
    table_rows: list
    metadata: dict
    quality_flag: str | None  # If set, chunk is excluded from review
```

**M2 enforces:** Only chunks with `ctd_section.upper().startswith("3.2.S.4")` and no `quality_flag` are reviewed.

---

## 4. M2 → M4 Contract

M2 findings are passed to M4 for consistency evaluation and memory storage.
M4 receives a `S4ReviewResult` containing a list of `Finding` objects.

Each `Finding` includes:
- `qa_status = PENDING` — M4 updates this after review
- `requires_human_review = True` — must not be changed to False without human sign-off
- `regulatory_evidence` — list of EvidencePassage with full provenance

---

## 5. M2 → M5 Contract

M5 provides expert-labelled gold queries for evaluation.
M5 supplies `GoldQuery` objects; M2 runs benchmarks and returns `BenchmarkReport`.

```python
class GoldQuery:
    query_id: str
    question: str
    relevant_chunk_ids: list[str]
    filters: EvidenceFilters

class BenchmarkReport:
    config: dict
    evaluated_queries: int
    aggregate: dict  # precision@k, recall@k, MRR, nDCG
    per_query: list[dict]
    caution: str     # Always includes expert-label caveat
```

**Current status:** Schema ready. Expert gold labels not yet provided by M5.

---

## 6. Mock Integration

Local integration mocks are available in `src/m2/team_simulation.py`.
These test M2 behaviour with synthetic M3 dossier input without requiring live M1/M3/M4/M5.

---

*Integration tests: `tests/test_advanced_release.py`, `tests/test_metrics_api_integration.py`*
