# SAHPRA Member 2 — Implementation Gap Analysis
**Date:** 2026-10-28  
**Version:** v1.1 → v1.2 transition  
**Auditor:** Claude Sonnet 4.6

---

## 1. Audit Scope

This analysis covers the complete `src/m2/` package, all scripts, all tests, all documentation and all
validation artefacts present in PROJECT_ROOT at v1.1.

---

## 2. Feature Status Summary

### 2.1 Evidence/RERA Agent (`retrieval.py`)

| Feature | Status | Notes |
|---------|--------|-------|
| Regulatory evidence queries | WORKING | `EvidenceService.retrieve()` fully implemented |
| Source-aware metadata filtering | WORKING | Authority, document_code, effective_on filters |
| CTD section filtering | WORKING | Via `EvidenceFilters.sections` |
| Document-version filtering | WORKING | Via `SourceRecord.version` and `effective_from/to` |
| Dense semantic retrieval | PARTIAL | Hash-demo embeddings only; real BGE blocked (no model weights) |
| Lexical BM25 retrieval | WORKING | `lexical_bm25()` implemented and tested |
| Hybrid ranking | WORKING | Weighted hybrid + RRF in `NavigationRanker` |
| Configurable reranking | WORKING | `CrossEncoderReranker` protocol; blocked if BGE not installed |
| Stable chunk identifiers | WORKING | SHA-256-based `stable_id()` |
| Exact regulatory citations | WORKING | `EvidencePassage.citation` field with source/page/version |
| Provenance and integrity checks | WORKING | `file_sha256`, `provenance_verified` field |
| Graceful insufficient-evidence response | WORKING | `EvidenceStatus.INSUFFICIENT_EVIDENCE` with `requires_human_review=True` |
| Explicit uncertainty | WORKING | `uncertainty` float on `Finding` |
| Structured outputs | WORKING | Full Pydantic v2 schema |
| M1 orchestration compatibility | WORKING | LangGraph adapters in `integration.py` |
| Source isolation (synthetic vs regulatory) | WORKING | `allow_synthetic` flag; separate synthetic path |

### 2.2 S.4 Control Agent (`s4.py`, `s4_rules.py`)

| Feature | Status | Notes |
|---------|--------|-------|
| 3.2.S.4.1 Specification review | WORKING | Finding generated with regulatory retrieval |
| 3.2.S.4.2 Analytical Procedures review | WORKING | Keyword extraction + evidence retrieval |
| 3.2.S.4.3 Validation review | WORKING | Validation terms regex + finding |
| 3.2.S.4.4 Batch Analyses review | WORKING | `compare_sponsor_batch_data()` numeric checks |
| 3.2.S.4.5 Justification of Specification | WORKING | Justification section retrieval |
| Finding identifier | WORKING | SHA-256-based `finding_id` |
| CTD subsection tagging | WORKING | `ctd_section` field |
| Sponsor evidence reference | WORKING | `SponsorEvidence` list in Finding |
| Retrieved regulatory evidence | WORKING | `regulatory_evidence` list in Finding |
| Exact citation/provenance | WORKING | Via `EvidencePassage.citation` |
| Assessment rationale | WORKING | `rationale` string |
| Uncertainty/confidence | WORKING | `uncertainty` float |
| Deficiency / evidence-gap description | WORKING | FindingStatus enum + rationale |
| QA status | WORKING | `qa_status` field (PENDING by default) |
| Human-review requirement | WORKING | `requires_human_review=True` always |
| LLM gap-analysis (optional Ollama) | PARTIAL | Wired but Ollama server may not be running |
| Invented numerical thresholds safeguard | WORKING | Explicit comment and architecture enforcement |

### 2.3 Regulatory Knowledge Base (`registry.py`, `storage.py`, `token_safe_index.py`)

| Feature | Status | Notes |
|---------|--------|-------|
| Source registration | WORKING | `SourceRegistry.register()` |
| PDF SHA-256 checksums | WORKING | 15 sources verified; `SHA256SUMS.txt` present |
| Source identifiers | WORKING | Stable `source_id` strings |
| Authority / provenance | WORKING | `SourceRecord.authority` + `provenance_verified` |
| Document versions | WORKING | `version` field |
| Page references | WORKING | `page` field in chunks and passages |
| Metadata completeness | WORKING | All required fields enforced by Pydantic |
| Applicability flags | WORKING | `approved`, `provenance_verified` |
| Duplicate record detection | WORKING | `register()` raises on conflicting metadata |
| Source status controls | WORKING | `eligible()` enforces `approved + provenance_verified` |
| Token-safe chunking | WORKING | `chunking.py` with word-token approximation |
| Native ChromaDB/BGE indexing | BLOCKED | Dependency install requires user permission; model weights not present |
| Persistent collection storage | PARTIAL | SQLite preview index exists; real Chroma blocked |
| Citation integrity | WORKING | Page anchors verified (554/554 in v1.1 audit) |
| Source filtering in retrieval | WORKING | `eligible()` method enforced |
| Source quarantine | WORKING | Research/unverified collections isolated |

### 2.4 Pharmacopoeial Source Governance (`pharmacopoeia.py`, `pharmacopoeia_service.py`)

| Feature | Status | Notes |
|---------|--------|-------|
| WHO monograph catalogue | WORKING | Four WHO references catalogued |
| BP/EP/Ph.Int metadata | PARTIAL | Catalogue structure ready; no licensed PDFs present |
| Substance identity verification | WORKING | Name/CAS/alias matching |
| Edition/revision tracking | WORKING | `edition`, `effective_date` fields |
| Source hash recording | WORKING | `source_hash` field |
| Licence rights status | WORKING | `rights_status` field |
| Regulatory applicability | WORKING | `applicable_jurisdictions` field |
| Reviewer status | WORKING | `review_status` enum |
| Incoming import folder | WORKING | `pharmacopoeia/incoming/` exists |
| Quarantine isolation | WORKING | Separate unverified collection |
| Auto-promotion safeguard | WORKING | `review_status != APPROVED` blocks promotion |

### 2.5 FastAPI / REST Interface (`api.py`, `runtime.py`)

| Feature | Status | Notes |
|---------|--------|-------|
| `/m2/evidence` POST endpoint | WORKING | Returns `EvidenceResult` |
| `/m2/s4/review` POST endpoint | WORKING | Returns `S4ReviewResult` |
| `/m2/phint/evidence` POST endpoint | WORKING | PhInt metadata lookup |
| `/m2/health` GET endpoint | WORKING | Returns runtime stats |
| Token authentication | WORKING | `M2_SERVICE_TOKEN` bearer check |
| LangGraph adapters | WORKING | `evidence_node()`, `s4_node()` |

### 2.6 Retrieval Benchmarking (`evaluation.py`, `technical_benchmark.py`, `experiments.py`)

| Feature | Status | Notes |
|---------|--------|-------|
| BM25 benchmark | WORKING | Runs against real corpus offline |
| TF-IDF word/char benchmarks | WORKING | In `technical_benchmark.py` |
| Hash-demo embedding benchmark | WORKING | Present |
| Hybrid RRF benchmark | WORKING | Present |
| Precision@K / Recall@K / MRR / nDCG | WORKING | Implemented in `evaluation.py` |
| Citation accuracy metric | WORKING | Present |
| Abstention behaviour tests | WORKING | `INSUFFICIENT_EVIDENCE` path covered |
| Expert-labelled evaluation | PENDING EXPERT REVIEW | Interface ready; no expert gold labels yet |
| Real BGE embedding benchmark | BLOCKED | Model weights not present |
| BGE reranker improvement measurement | BLOCKED | Reranker model not available |
| Latency measurement | PARTIAL | Offline benchmark timing present |

### 2.7 Testing

| Area | Tests | Pass | Fail | Blocked |
|------|-------|------|------|---------|
| Source registration | test_registry_chunking.py | PASS | — | — |
| PDF integrity | test_full_corpus_v05.py | PASS | — | — |
| Chunking | test_registry_chunking.py | PASS | — | — |
| Embeddings (hash-demo) | test_collection_v04.py | PASS | — | — |
| Retrieval (BM25/hybrid) | test_retrieval.py | PASS | — | — |
| Metadata filtering | test_retrieval.py | PASS | — | — |
| Citations | test_token_safe_and_citation_v11.py | PASS | — | — |
| Evidence abstention | test_retrieval.py | PASS | — | — |
| S.4 structured findings | test_s4.py | PASS | — | — |
| Numerical comparison safeguards | test_s4.py | PASS | — | — |
| Source quarantine | test_compendia_ingest.py | PASS | — | — |
| FastAPI endpoints | test_metrics_api_integration.py | PASS | — | — |
| Integration contracts | test_advanced_release.py | PASS | — | — |
| Database persistence | test_collection_v04.py | PASS | — | — |
| Unicode JSONL read | test_technical_benchmark_v06.py | FIXED | — | — |
| Real ChromaDB/BGE | — | — | — | BLOCKED |
| Expert-label evaluation | — | — | — | PENDING M5 |

**Baseline:** 136 passed, 1 failed. After Unicode fix: 137 expected to pass.

---

## 3. Defects Found

### DEF-001: UnicodeDecodeError in benchmark JSONL read (FIXED)
- **File:** `src/m2/technical_benchmark.py` line 184, 186
- **Cause:** `.read_text()` without `encoding="utf-8"` on Windows uses cp1252 which cannot decode Unicode characters in the JSONL file.
- **Fix:** Added `encoding="utf-8"` to both `read_text()` calls.
- **Status:** FIXED in v1.2.

---

## 4. External Dependencies / Blockers

| Item | Reason Blocked | Required User Action |
|------|---------------|---------------------|
| Real ChromaDB/BGE indexing | `sentence-transformers` and `chromadb` model weights (~1.3 GB) not present | Run: `pip install -e ".[vector,models]"` and `python scripts/build_real_chroma_on_user_pc.py` on internet-connected machine |
| BGE reranker | `BAAI/bge-reranker-large` model not downloaded | Download on internet-connected machine |
| Licensed pharmacopoeial PDFs (BP, EP) | Require valid institutional licence | Obtain from publisher and place in `pharmacopoeia/incoming/` |
| Expert-labelled evaluation queries | Member 5 not yet integrated | Coordinate with M5 per `docs/M5_EXPERT_LABELS_HANDOFF_v0.6.md` |
| Production deployment | Requires M1 orchestration ratification | Coordinate with M1 |
| Ollama LLM server | Optional gap-analysis feature | Install Ollama locally if gap narrative needed |

---

## 5. Missing Required Documentation (to be created)

The following files specified in the Master Instruction are not yet present and will be created:

- `docs/00_HANDOVER_README.md`
- `docs/01_PROJECT_SCOPE_AND_EXPECTATIONS.md`
- `docs/02_SYSTEM_ARCHITECTURE.md`
- `docs/03_MEMBER2_REQUIREMENTS_TRACEABILITY.md`
- `docs/04_RERA_AGENT_DESIGN.md`
- `docs/05_S4_CONTROL_AGENT_DESIGN.md`
- `docs/06_M1_M3_M4_M5_INTEGRATION_CONTRACTS.md`
- `docs/07_REGULATORY_KNOWLEDGE_BASE_DESIGN.md`
- `docs/08_SOURCE_GOVERNANCE_AND_PROVENANCE.md`
- `docs/09_SECURITY_AND_HUMAN_REVIEW.md`
- `docs/10_TEST_AND_EVALUATION_PLAN.md`
- `docs/11_DEPLOYMENT_AND_OPERATIONS.md`
- `docs/12_FINAL_ACCEPTANCE_CHECKLIST.md`
- `docs/13_CLAUDE_IMPLEMENTATION_REPORT.md`
- `docs/14_DATABASE_AND_MODEL_CONFIGURATION.md`
- `docs/15_PHARMACOPOEIAL_IMPORT_GUIDE.md`
- `docs/16_KNOWN_LIMITATIONS_AND_DEPENDENCIES.md`
- `docs/17_RELEASE_AND_REPRODUCIBILITY_REPORT.md`

---

*Generated by Claude Sonnet 4.6, 2026-10-28*
