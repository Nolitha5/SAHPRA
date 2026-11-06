# System Architecture — Member 2
**Version:** 1.2 | **Date:** 2026-10-28

---

## 1. Overview

Member 2 is a self-contained Python package (`src/m2/`) exposing three logical subsystems:

```
┌─────────────────────────────────────────────────────────┐
│                    M1 Orchestration                      │
│                 (LangGraph / FastAPI)                    │
└──────────┬────────────────────┬────────────────────────-┘
           │ EvidenceRequest    │ S4ReviewRequest
           ▼                    ▼
┌─────────────────┐  ┌──────────────────────────────────┐
│  Evidence/RERA  │  │       S.4 Control Agent           │
│  EvidenceService│  │      S4ControlAgent               │
└────────┬────────┘  └──────────────┬───────────────────┘
         │                          │ calls Evidence/RERA
         ▼                          │
┌─────────────────────────────────────────────────────────┐
│               Regulatory Knowledge Base                  │
│  SourceRegistry  ─  VectorStore  ─  ChunkingPipeline    │
│  (registry.py)     (storage.py)    (chunking.py)        │
└─────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│         Regulatory Source Documents (PDFs)               │
│     15 documents, 554 page-anchored chunks               │
│     SHA-256 verified, provenance-recorded                │
└─────────────────────────────────────────────────────────┘
```

## 2. Module Map

| Module | Responsibility |
|--------|----------------|
| `schemas.py` | Shared Pydantic v2 data contracts |
| `registry.py` | Source registration, eligibility, provenance |
| `storage.py` | VectorStore protocol (in-memory and SQLite) |
| `chunking.py` | Token-safe, page-anchored chunk production |
| `retrieval.py` | BM25 + hash-demo hybrid Evidence/RERA service |
| `s4.py` | S.4 Control agent (all 5 subsections) |
| `s4_rules.py` | Numeric batch analysis cross-checks |
| `pharmacopoeia.py` | Pharmacopoeial catalogue schema and management |
| `pharmacopoeia_service.py` | Compendial evidence lookup interface |
| `api.py` | FastAPI router: /evidence, /s4/review, /phint/evidence |
| `runtime.py` | AppConfig + M2Runtime factory |
| `integration.py` | LangGraph-compatible evidence_node, s4_node |
| `embeddings.py` | Embedding protocols + BGE wrapper (if available) |
| `evaluation.py` | Precision@K, Recall@K, MRR, nDCG metrics |
| `technical_benchmark.py` | Offline benchmark runner for real corpus |
| `experiments.py` | Multi-model experiment comparison scaffold |
| `token_safe_index.py` | Token-budget-aware chunking helper |
| `citation_audit.py` | Page-anchor citation integrity verifier |
| `sqlite_vectors.py` | SQLite-backed lightweight vector store |
| `curation.py` | Source curation and status management |

## 3. Data Flow — Evidence Retrieval

```
EvidenceRequest
    → SourceRegistry.eligible() (filters unapproved/unverified sources)
    → VectorStore.all_chunks()  (fetch all eligible chunks)
    → lexical_bm25() + semantic similarity (hybrid scoring)
    → optional CrossEncoderReranker.rank()
    → top_k selection
    → EvidenceResult with EvidencePassage list
```

## 4. Data Flow — S.4 Control

```
S4ReviewRequest (dossier_chunks)
    → filter to 3.2.S.4.* sections
    → extract_s4_fields() (keyword hints)
    → for each S.4.x subsection:
        → EvidenceService.retrieve() (regulatory evidence)
        → compare_sponsor_batch_data() (numeric checks, S.4.4)
        → construct Finding with status, rationale, uncertainty
    → S4ReviewResult (all findings, all require_human_review=True)
```

## 5. Integration Boundaries

| Interface | Direction | Protocol |
|-----------|-----------|---------|
| M1 → M2 EvidenceRequest | inbound | FastAPI POST /m2/evidence or LangGraph evidence_node |
| M1 → M2 S4ReviewRequest | inbound | FastAPI POST /m2/s4/review or LangGraph s4_node |
| M3 → M2 DossierChunk | inbound | Pydantic schema (passed in S4ReviewRequest.dossier_chunks) |
| M2 → M4 Finding | outbound | Pydantic Finding schema (in S4ReviewResult.findings) |
| M2 → M5 EvaluationInterface | outbound | GoldQuery / BenchmarkReport schemas |

---

*All inter-member data contracts are provisional pending M1 ratification.*
