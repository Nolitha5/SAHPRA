# Integration contracts — M1/M2/M3/M4/M5 (provisional v0.1)

**Authority:** `QA-RAG_Team_Delegation.pdf` pp.1–2 and the five 13 October 2026 member specifications. Code implements provisional concrete fields; M1 retains authority to ratify shared Pydantic models.

## M1 ↔ M2 — Orchestrator, Evidence, S.4

- `EvidenceService.retrieve(EvidenceRequest) -> EvidenceResult` in `m2.retrieval`.
- `S4ControlAgent.review(S4ReviewRequest) -> S4ReviewResult` in `m2.s4`.
- `m2.integration.evidence_node(runtime)` accepts state key `evidence_request` and returns state update key `evidence_result`.
- `m2.integration.s4_node(runtime)` accepts `s4_request` and returns state updates `s4_result` and `findings`.
- M1's API owner chooses between local Python calls and FastAPI router; **RKB internals are not exposed as the public integration contract**.
- M1 must supply shared agent state, error routing, access control, parallel agent scheduling and human-gate state. M2 does not provide the final `/analyse` endpoint.

## M3 → M2 — documents vs regulation

- `DossierChunk` (sponsor): `chunk_id, document_id, ctd_section, text, page, kind, table_rows, metadata, quality_flag`.
- `RegulatoryChunk` (regulatory): `chunk_id, source_id, text, section, page, chunk_kind, checksum, metadata`.
- **Separate these types**. `DossierChunk` is sent to the S.4 agent for reasoning, NEVER implicitly indexed into RKB. `RegulatoryChunk` may only be indexed if its source is in M2's approved source manifest.
- CTD sections are uppercase canonical strings such as `3.2.S.4.1`; source location must be preserved. Document ingestion, OCR, redaction, table extraction and quality flags are M3's responsibility.
- M3 should generate unique stable chunk IDs, preserve source location, and report extraction confidence/quality flags. `table_rows` consists of dictionaries retaining exact data, units and provenance. A failed extraction is NOT "empty compliant dossier".
- Regulatory-source parsing can reuse M3's generic extraction service. M2 still owns approved-source registration, regulatory chunking experiments, embedding and indexing.

## M2 → M4 — scoring and memory

- M2 supplies `EvidenceResult` and S.4 `Finding` outputs, including passage texts, source identity and stable evidence/chunk IDs.
- M4 owns case memory, audit, evaluation harness and baseline A–D orchestration. M2 provides exportable per-query metrics and full candidate lists for metric computation.
- M2's evaluation JSON is in `BenchmarkReport` format; experiment reports include exact model, chunk size, overlap, tokenizer and reranking flags.
- M2 does not persist assessor decisions, case history or M4's evaluation state.

## M2 ↔ M5 — QA/domain

- M5 uses the same `EvidenceService` for S.5 pharmacopeia versions. `EvidenceFilters.effective_on` may constrain historical source applicability; if effective dates are unknown, the service abstains rather than making a false version claim.
- QA/Critic receives both exact `SponsorEvidence` and `EvidencePassage` references for a Finding.
- `Finding.qa_status` is **workflow QA** (`PENDING`, `PASS`, `FLAG`, `ESCALATE`). Evidence sufficiency is **separate** (`FOUND`, `INSUFFICIENT_EVIDENCE`, `ERROR`); regulatory disposition is exclusively human. If M5 elects verified/partial/unsupported/conflicting labels, map those to a separate field rather than overloading QA workflow flags.
- M5 supplies expert-approved source list, query-evidence anchors, golden tests, QA rubric and human review of model-generated issues.

## Shared schema ownership and adaptation

The team's `Finding` may differ from our provisional `m2.schemas.Finding`. M1 should publish its canonical Pydantic v2 `Finding`, then build a single adapter with explicit field mapping in `m2.integration`. Avoid forking multiple incompatible schemas. Do NOT silently coerce missing provenance or QA status into passing values. Use Pydantic's `model_validate()` for interoperability tests.

## Handling failure and uncertainty

- Missing source, no approved applicable source, low lexical-relevance → `INSUFFICIENT_EVIDENCE`, `requires_human_review=true`, `evidence=[]`.
- Index I/O/model failure → `ERROR`, `requires_human_review=true`, `evidence=[]`.
- A finding based on available sponsor evidence remains provisional; `QA=PENDING` even when evidence retrieved.
- Missing S.4 material or bad extraction is a completeness/ingestion investigation, **not** automatic noncompliance.

## Integration test handshake

1. M3 provides one real de-identified dossier extract tagged `3.2.S.1` and `3.2.S.4.1–5`.
2. M2 loads one verified guideline PDF into RKB, returns an authentic passage + locator for an M1 S.1 query.
3. M1 executes `EvidenceService.retrieve` inside LangGraph and routes it to S.1.
4. M2's S.4 node returns at least one `Finding` using M1's schema.
5. M5 QA/Critic checks citations and M1 routes to Human Gate; M4 records the outcome.
6. M4 verifies the trace can be exported and evaluated. Every failure is observable, not silently swallowed.

Acceptance must be demonstrated on the actual shared mono-repo; local mock tests do not replace this handshake.
