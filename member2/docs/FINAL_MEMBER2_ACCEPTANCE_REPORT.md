# SAHPRA Agentic QA-RAG — Member 2 Final Acceptance Report
**Version:** v1.3.1  
**Date:** 2026-10-28  
**Prepared by:** SAHPRA Member 2 QA-RAG System (automated validation)  
**Status:** VALIDATED — READY FOR ACCEPTANCE REVIEW

---

## 1. Executive Summary

Member 2 of the SAHPRA Agentic QA-RAG pipeline has been completed, validated and released at v1.3.1. The implementation covers:

- **Regulatory knowledge base:** 15 ICH/EMA/SAHPRA guidance documents, 554 chunks, embedded with BAAI/bge-large-en-v1.5 (1024-dim) and indexed in ChromaDB. Collection: `regulatory_technical_unapproved`.
- **Sponsor dossier knowledge base:** 45 CTD section 3.2.S PDFs (Valsartan, Amlodipine, Hydrochlorothiazide), 2064 chunks, separately indexed in ChromaDB. Collection: `sponsor_dossier_unverified`.
- **Retrieval benchmark:** 30 researcher-authored document-navigation probes evaluated with corrected source-level metrics (prior run reporting Recall>1.0 superseded).
- **Quarantine store:** 5 HTML sources quarantined with `approved=False`, never loaded into any vector collection.
- **Release ZIP:** `releases/SAHPRA_Member2_KnowledgeBase_Integration_v1.3.1.zip` (excludes ChromaDB indexes and BGE model weights — rebuild instructions provided).

---

## 2. Scope and Authorised Boundaries

| Boundary | Value |
|---|---|
| Authorised project directory | `C:\Users\Staff 101\OneDrive\Desktop\SAHPRA_Member2_TokenSafe_CitationValidated_v1.1` |
| Pharmacy read source (read-only) | `C:\Users\Staff 101\Downloads\Pharmacy` |
| Python version | 3.13.2 / Windows 11 |
| ChromaDB version | 1.5.9 |
| Embedding model | BAAI/bge-large-en-v1.5 (1024-dim) |

**Security constraints enforced:**
- No autonomous approval or rejection of medicines
- Dossier data isolated from regulatory collection; not included in release ZIP
- All 5 HTML sources quarantined (`approved=False`, `provenance_verified=False`)
- No redistribution of licensed pharmacopoeial text
- Every source has a recorded review status

---

## 3. Regulatory Knowledge Base

### 3.1 Source Inventory

| Source ID | Document | Class | Chunks | Hash Verified |
|---|---|---|---|---|
| ICH-Q1A-R2 | ICH Q1A(R2) Stability Testing | A | ≥30 | ✓ |
| ICH-Q1B | ICH Q1B Photostability | A | ≥10 | ✓ |
| ICH-Q2R1 | ICH Q2(R1) Validation | A | ≥20 | ✓ |
| ICH-Q3A-R2 | ICH Q3A(R2) Impurities Drug Substance | A | ≥15 | ✓ |
| ICH-Q3B-R2 | ICH Q3B(R2) Impurities Drug Products | A | ≥15 | ✓ |
| ICH-Q3C-R8 | ICH Q3C(R8) Residual Solvents | A | ≥15 | ✓ |
| ICH-Q3D-R1 | ICH Q3D(R1) Elemental Impurities | A | ≥20 | ✓ |
| ICH-Q6A | ICH Q6A Specifications | A | ≥30 | ✓ |
| ICH-M4Q-R1 | ICH M4Q(R1) CTD Quality | A | ≥20 | ✓ |
| ICH-Q8R2 | ICH Q8(R2) Pharmaceutical Development | A | ≥20 | ✓ |
| ICH-Q9R1 | ICH Q9(R1) Quality Risk Management | A | ≥15 | ✓ |
| ICH-Q10 | ICH Q10 Pharmaceutical Quality System | A | ≥15 | ✓ |
| ICH-Q11 | ICH Q11 Development and Manufacture | A | ≥20 | ✓ |
| ICH-Q14 | ICH Q14 Analytical Procedure Development | A | ≥20 | ✓ |
| EMA-SAHPRA-GMP | EMA/SAHPRA GMP Guidance | A | ≥30 | ✓ |

**Total:** 15 sources, 554 chunks, backend=ACTUAL_CHROMADB, model=BAAI/bge-large-en-v1.5, dimension=1024.

*Verified in:* `local_indexes/regulatory_chroma/ACTUAL_CHROMA_RUN.json`

### 3.2 Collection Properties

```json
{
  "backend": "ACTUAL_CHROMADB",
  "model": "BAAI/bge-large-en-v1.5",
  "vector_dimension": 1024,
  "collection": "regulatory_technical_unapproved-87028c6ff4ca",
  "chunk_count": 554,
  "source_count": 15,
  "verified_source_hashes": true,
  "regulatory_source_approval": false
}
```

---

## 4. Sponsor Dossier Knowledge Base (Class D)

**IMPORTANT: Class D sources are sponsor-provided dossier sections. They are evidence in the application under review — not regulatory authority guidance. Human review is required before any result influences a regulatory assessment.**

| Substance | PDFs | Chunks |
|---|---|---|
| Valsartan | 14 | ≥163 |
| Amlodipine | 16 | ≥927 |
| Hydrochlorothiazide | 15 | ≥308 |
| **Total** | **45** | **2064** |

Collection: `sponsor_dossier_unverified-<hash>` (separate from regulatory collection).  
Metadata flags on every chunk: `classification=D_SPONSOR_DOSSIER`, `approved=False`, `requires_human_review=True`.

---

## 5. Quarantined Sources (Class C/Unofficial)

Five HTML references from unofficial web sources are quarantined and **not** loaded into any vector collection:

| File | Source | Status |
|---|---|---|
| amlodipine-besilate-tablets [webofpharma.com].html | webofpharma.com | QUARANTINED |
| amlodipine-oral-solution [webofpharma.com].html | webofpharma.com | QUARANTINED |
| hydrochlorothiazide-tablets.html | Unknown | QUARANTINED |
| valsartan-capsules.html | Unknown | QUARANTINED |
| valsartan-tablets.html | Unknown | QUARANTINED |

All five have `approved=False` and `provenance_verified=False` in `pharmacopoeia/incoming/COPY_MANIFEST.json`.

---

## 6. Retrieval Benchmark Results

**Label:** researcher_authored_technical_navigation  
**Disclaimer:** 30 researcher-authored document-navigation probes. NOT expert-labelled regulatory accuracy assessment. Source-level binary relevance (one relevant source per query).

**Superseded:** Prior `RETRIEVAL_EXPERIMENTS_v1_3.json` reported Recall@K > 1.0 due to counting multiple chunks from the same source as separate relevant items. That file is superseded.

### 6.1 Corrected Metrics (source-level deduplication)

| Method | MRR | Hit@1 | Hit@3 | Hit@5 | nDCG@5 | Hit@10 |
|---|---|---|---|---|---|---|
| BM25 | 0.8317 | 0.7333 | 0.9000 | 0.9667 | 0.8614 | 1.0000 |
| BGE (bge-large-en-v1.5) | 0.8778 | 0.8000 | 0.9333 | 1.0000 | 0.9085 | 1.0000 |

*Full per-query results retained in:* `validation/FINAL_RETRIEVAL_BENCHMARK.json`

### 6.2 Metric Definitions

- **Hit@K**: 1 if the correct source document appears in the top-K unique source-ranked results
- **MRR**: Reciprocal rank of the first relevant source in the de-duplicated source ranking
- **source-P@K**: Fraction of unique top-K sources that match the expected source
- **source-R@K**: Fraction of expected sources found in unique top-K (denominator = 1 per query here)
- **source-nDCG@K**: Normalised DCG at source level with binary relevance

---

## 7. Test Results

### 7.1 Full Regression Suite (v1.2 + v1.3 KB integration)

Executed: `python -m pytest tests/ -v --tb=short` (excluding S.4 evidence smoke — requires dossier build)

| Result | Count |
|---|---|
| **Passed** | **186** |
| Failed | 0 |
| Skipped | 0 |
| Warnings | 3 (httpx + FutureWarning — non-blocking) |

*Full output:* `validation/FINAL_REGRESSION_RESULTS.txt`

### 7.2 v1.3 KB Integration Tests

| Suite | Passed | Failed | Skipped |
|---|---|---|---|
| TestRegulatoryChromaReport (4 tests) | 4 | 0 | 0 |
| TestDossierChromaReport (6 tests) | 6 | 0 | 0 |
| TestS4EvidenceSmoke (16 tests) | 16 | 0 | 0 |

### 7.3 S.4 Evidence Smoke Test

Verifies correct distinction among:
- **Sponsor evidence (Class D):** retrieved only from `dossier_chroma`; `classification=D_SPONSOR_DOSSIER`, `approved=False`, `requires_human_review=True`
- **Regulatory evidence (Class A):** retrieved only from `regulatory_chroma`; no dossier chunks; `chunk_kind != dossier`
- **Provisional findings (quarantine):** HTML sources never appear in any vector collection
- **Human-review annotation:** all dossier search results carry `requires_human_review=True`

---

## 8. Release Contents

### 8.1 v1.3.1 ZIP

**File:** `releases/SAHPRA_Member2_KnowledgeBase_Integration_v1.3.1.zip`  
**SHA-256:** `ba0e78e8cc40d12196114ff034267496d5d817c69d18dd2eba1378aec42b4ce7`  
**Files:** 278  
**Size:** 46.6 MB

**Intentional exclusions (with rebuild commands):**

| Excluded path | Size | Rebuild command |
|---|---|---|
| `local_indexes/regulatory_chroma/` | ~50MB | `python scripts/build_real_chroma.py` |
| `local_indexes/dossier_chroma/` | ~200MB | `python scripts/build_dossier_chroma.py` |
| `models/bge-large-en-v1.5/` | ~1.3GB | Auto-downloaded on first run via sentence-transformers |
| `pharmacopoeia/incoming/raw_from_pharmacy/` | ~320MB | Not redistributable — copy from authorised Pharmacy folder |

**Included:**
- All source code (`src/`, `tests/`, `scripts/`)
- Regulatory JSONL corpus (`artifacts/real_corpus/REGULATORY_CHUNKS.jsonl`)
- Documentation (`docs/`, 18 files)
- Validation artefacts (`validation/`)
- Probe file (`examples/researcher_navigation_probes_v0.6.json`)
- Source inventory (`regulatory_sources/PHARMACY_SOURCE_INVENTORY.csv`)
- Copy manifest (`pharmacopoeia/incoming/COPY_MANIFEST.json`)
- Quarantine HTML files (`pharmacopoeia/quarantine/`)

---

## 9. Known Limitations

1. **No expert-validated ground truth:** Retrieval metrics are based on researcher-authored navigation probes. Results cannot be cited as regulatory-quality performance benchmarks.
2. **BGE model not included in ZIP:** Requires download (~1.3GB) on first use; offline operation requires pre-downloaded weights.
3. **ChromaDB lock risk under OneDrive sync:** `local_indexes/` should be excluded from OneDrive sync or the process should be stopped before syncing.
4. **Dossier identity not independently verified:** Dossier PDFs were copied from the authorised Pharmacy folder; their identity has not been independently authenticated against SAHPRA submission records.
5. **No passage-level gold labels:** nDCG is computed at source (document) level only; passage-level ranking quality is not assessed.

---

## 10. Traceability

| Artefact | Description | Location |
|---|---|---|
| `ACTUAL_CHROMA_RUN.json` | Regulatory ChromaDB build report | `local_indexes/regulatory_chroma/` |
| `DOSSIER_CHROMA_RUN.json` | Dossier ChromaDB build report | `local_indexes/dossier_chroma/` |
| `FINAL_RETRIEVAL_BENCHMARK.json` | Corrected retrieval metrics | `validation/` |
| `FINAL_REGRESSION_RESULTS.txt` | Full test suite output | `validation/` |
| `FINAL_SOURCE_AND_CITATION_AUDIT.json` | Source hash audit | `validation/` |
| `PHARMACY_SOURCE_INVENTORY.csv` | Complete source inventory | `regulatory_sources/` |
| `COPY_MANIFEST.json` | SHA-256-verified copy manifest | `pharmacopoeia/incoming/` |
| `V1_2_RELEASE_COMPLETENESS_AUDIT.json` | v1.2 release audit | `validation/` |

---

*This report was generated automatically as part of the v1.3.1 validation pipeline. All findings are machine-generated and require human review before use in regulatory decision-making.*
