# Member 2 Requirements Traceability Matrix
**Version:** 1.2 | **Date:** 2026-10-28

| Req ID | Requirement | Implementation | Status |
|--------|-------------|---------------|--------|
| M2-R01 | Evidence/RERA regulatory evidence queries | `retrieval.EvidenceService.retrieve()` | PASS |
| M2-R02 | Source-aware metadata filtering | `registry.SourceRegistry.eligible()` | PASS |
| M2-R03 | CTD section filtering | `EvidenceFilters.sections` | PASS |
| M2-R04 | Document-version and date filtering | `effective_from/to` in SourceRecord | PASS |
| M2-R05 | Dense semantic retrieval | Hash-demo; BGE blocked | PARTIAL |
| M2-R06 | Lexical BM25 retrieval | `retrieval.lexical_bm25()` | PASS |
| M2-R07 | Hybrid ranking | Weighted hybrid + RRF | PASS |
| M2-R08 | Configurable reranking | `CrossEncoderReranker` protocol | PARTIAL (model absent) |
| M2-R09 | Stable chunk/passage identifiers | `chunking.stable_id()` SHA-256 | PASS |
| M2-R10 | Exact regulatory citations | `EvidencePassage.citation` with source/page/version | PASS |
| M2-R11 | Provenance and source-integrity checks | `file_sha256`, `provenance_verified` | PASS |
| M2-R12 | Graceful insufficient-evidence response | `EvidenceStatus.INSUFFICIENT_EVIDENCE` | PASS |
| M2-R13 | Explicit uncertainty | `Finding.uncertainty` float field | PASS |
| M2-R14 | Structured outputs (Pydantic) | Full Pydantic v2 schema in `schemas.py` | PASS |
| M2-R15 | M1 LangGraph compatibility | `integration.evidence_node()`, `s4_node()` | PASS |
| M2-R16 | 3.2.S.4.1 Specification review | `s4.S4ControlAgent.review()` — S.4.1 branch | PASS |
| M2-R17 | 3.2.S.4.2 Analytical Procedures review | S.4.2 branch with method regex extraction | PASS |
| M2-R18 | 3.2.S.4.3 Validation of Analytical Procedures | S.4.3 branch with validation regex | PASS |
| M2-R19 | 3.2.S.4.4 Batch Analyses review | S.4.4 + `s4_rules.compare_sponsor_batch_data()` | PASS |
| M2-R20 | 3.2.S.4.5 Justification of Specification | S.4.5 branch | PASS |
| M2-R21 | Finding includes all required fields | All fields present in `schemas.Finding` | PASS |
| M2-R22 | No invented numerical thresholds | Architecture enforcement + explicit comments | PASS |
| M2-R23 | SHA-256 checksum validation | 15 PDFs verified; `SHA256SUMS.txt` | PASS |
| M2-R24 | ChromaDB persistent indexing | SQLite preview; real Chroma blocked | PARTIAL |
| M2-R25 | Token-safe chunking | `chunking.section_chunks()` word-token approx. | PASS |
| M2-R26 | 554 page-anchor citation audit | v1.1 audit: 554/554 verified | PASS |
| M2-R27 | Pharmacopoeial source governance | `pharmacopoeia.py` + catalogue | PASS |
| M2-R28 | WHO monograph references | 4 WHO references catalogued (DNS blocked download) | PARTIAL |
| M2-R29 | Incoming pharmacopoeial import folder | `pharmacopoeia/incoming/` exists | PASS |
| M2-R30 | Source quarantine for unverified material | Separate research collection | PASS |
| M2-R31 | FastAPI REST interface | `/m2/evidence`, `/m2/s4/review`, `/m2/health` | PASS |
| M2-R32 | Token authentication | `M2_SERVICE_TOKEN` bearer via Header | PASS |
| M2-R33 | Precision@K / Recall@K / MRR / nDCG metrics | `evaluation.py` | PASS |
| M2-R34 | Expert-labelled evaluation interface | Schema ready; gold labels pending M5 | PENDING M5 |
| M2-R35 | Real BGE embedding benchmark | Script ready; model weights needed | BLOCKED |
| M2-R36 | M3 dossier ingestion interface | `DossierChunk` + `S4ReviewRequest` schema | PASS |
| M2-R37 | M4 Finding handoff | `Finding` schema passed in `S4ReviewResult` | PASS |
| M2-R38 | M5 evaluation handoff | `GoldQuery` + `BenchmarkReport` schemas | PASS |
| M2-R39 | Automated regression tests (137 tests) | `tests/` — 137 pass (after DEF-001 fix) | PASS |
| M2-R40 | No autonomous regulatory approval | Architecture enforced; `requires_human_review=True` always | PASS |

**Legend:** PASS = Implemented and tested. PARTIAL = Implemented, incompletely validated. BLOCKED = External dependency. PENDING M5 = Awaiting Member 5.
