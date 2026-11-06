# Member-2 team handoff instructions

## To M1 (integration lead)

Use `m2.integration.evidence_node(runtime)` in LangGraph. The underlying RKB index and source registry are owned by M2 and need not be accessed directly by section agents. Use `s4_node` for the S.4 specialist. Ratify/adapt the Pydantic `Finding` model and define the canonical request/response contract. Include M2 calls in one shared FastAPI `/analyse` workflow, not a separate independently maintained orchestration graph. Verify source/model configuration and call failures in the main runtime.

## To M3 (ingestion)

Return validated `DossierChunk` records with section tags, stable `document_id`, `chunk_id`, page, structured tables, and quality flags. Never blend sponsor dossier content into M2's authoritative regulatory RKB. Provide generic PDF extraction for regulation indexing when asked; M2 retains corpus approval and vector indexing. Arrange joint sample reviews of CTD S.4.1–S.4.5.

## To M4 (memory + evaluation)

Consume `S4ReviewResult.findings`, `EvidenceResult` and `artifacts/*` benchmark results. Own persistent audit memory and full A–D experiments. Request sources/labels/provenance for failed retrievals from M2; classify failures retrieval/extraction/routing/reasoning/QA with whole team. Separate metrics obtained on synthetic examples from expert-labelled real metrics.

## To M5 (QA/domain/UI)

Use RERA to retrieve applicable pharmacopoeial editions for S.5. A missing effective date means edition currentness cannot be inferred. Source approvals and gold query-evidence anchors must be reviewed by qualified domain assessors. QA stamps `Finding.qa_status` only after verification. UI displays the exact source and sponsor passages and never silently hides flags. Human disposition is recorded by M4 through M1.

## Deliverable locations

- API and adapter: `src/m2/api.py` and `src/m2/integration.py`
- Common temporary schema: `src/m2/schemas.py`
- Source approval instructions: `docs/SOURCE_POLICY.md`
- Team decisions that may change: `docs/PROVISIONAL_DECISIONS.md`
- Test command: `python -m pytest -q`
- Real performance experiment instructions: `docs/IMPLEMENTATION_RUNBOOK.md`

## Suggested meeting agenda

Ratify the shared `Finding` schema and M3 chunk schema; choose exact Ollama model, RKB indexing permission and source versions; select a real Tier-0 query with ground-truth citation; set M1 repository branch conventions; agree API auth and access boundaries; then run the one-thin-thread acceptance gate.
