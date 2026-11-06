# Test and Evaluation Plan
**Version:** 1.2 | **Date:** 2026-10-28

---

## 1. Test Suite Summary

**Run command:** `python -m pytest tests/ -q`  
**Baseline (v1.1):** 136 passed, 1 failed (Unicode encoding bug)  
**After v1.2 fix:** 137 passed, 0 failed (expected)

---

## 2. Test Files and Coverage

| File | Coverage Area | Expected Result |
|------|--------------|-----------------|
| `test_registry_chunking.py` | Source registration, chunking, SHA-256 IDs | PASS |
| `test_retrieval.py` | Evidence retrieval, filtering, abstention | PASS |
| `test_s4.py` | S.4 Control agent, all 5 subsections, numeric checks | PASS |
| `test_full_corpus_v05.py` | 15-source corpus integrity and indexing | PASS |
| `test_collection_v04.py` | SQLite hash-demo collection persistence | PASS |
| `test_token_safe_and_citation_v11.py` | Token-safe chunking + page citation audit | PASS |
| `test_metrics_api_integration.py` | FastAPI endpoint integration | PASS |
| `test_advanced_release.py` | Release validation and integration contracts | PASS |
| `test_assessor_checklist.py` | Assessor checklist output | PASS |
| `test_compendia_ingest.py` | Pharmacopoeial source ingestion and quarantine | PASS |
| `test_technical_benchmark_v06.py` | Offline BM25/TF-IDF/hybrid benchmark | PASS (after DEF-001 fix) |
| `test_deferred_compendia_v10.py` | Deferred pharmacopoeial corpus handoff | PASS |
| `test_pharmacopoeia_v07.py` | WHO monograph catalogue | PASS |
| `test_real_corpus.py` | Real PDF corpus construction | PASS |
| `test_real_uploaded_pdfs.py` | SHA-256 verification of uploaded PDFs | PASS |
| `test_security.py` | API auth, token checks | PASS |
| `test_who_acquisition_v08.py` | WHO monograph acquisition (DNS-blocked gracefully) | PASS |
| `test_official_queue.py` | Official source acquisition queue | PASS |

---

## 3. Retrieval Evaluation Metrics

Implemented in `evaluation.py`:

| Metric | Formula | Current Data Source |
|--------|---------|---------------------|
| Precision@K | TP / K | Researcher-authored navigation probes |
| Recall@K | TP / relevant | Researcher-authored navigation probes |
| MRR | mean(1/rank_first_relevant) | Same |
| nDCG | normalised DCG | Same |
| Citation accuracy | % passages with valid citation | Audit data |
| Abstention rate | % INSUFFICIENT_EVIDENCE responses | Test suite |

**Important:** Current benchmark results use researcher-authored navigation probes, not expert-labelled gold queries.
Expert performance must be reported separately once M5 supplies gold labels.

---

## 4. Offline Benchmark Results

From `validation/BENCHMARK_CONSOLE.json` (researcher-authored probes, real corpus):

- BM25, TF-IDF word, TF-IDF char, hash-demo and hybrid RRF modes measured
- All modes produce non-zero recall on researcher probes
- Results are NOT equivalent to expert-validated regulatory performance
- BGE-large and BGE-M3 benchmarks blocked (model weights not present)

---

## 5. Pending Evaluation Gates

| Gate | Status | Unblocked By |
|------|--------|-------------|
| Expert-labelled evaluation | PENDING M5 | M5 supplies GoldQuery set |
| Real BGE embedding benchmark | BLOCKED | User installs `[vector,models]` + downloads weights |
| BGE reranker improvement delta | BLOCKED | Same as above |
| Live M1–M5 integration test | PENDING TEAM | Full team coordination |

---

## 6. Reproduction Commands

```powershell
# Full test suite
python -m pytest tests/ -v

# Benchmark only
python -m pytest tests/test_technical_benchmark_v06.py -v

# Citation audit
python -c "from m2.citation_audit import run_audit; run_audit('.')"

# Offline benchmark
python scripts/run_offline_benchmark.py --root .
```
