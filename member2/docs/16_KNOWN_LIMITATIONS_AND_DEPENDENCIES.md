# Known Limitations and External Dependencies
**Version:** 1.3 | **Date:** 2026-10-28

---

## 1. Blocked External Dependencies

| Dependency | Why Needed | User Action |
|------------|-----------|-------------|
| `BAAI/bge-large-en-v1.5` model weights | Real semantic embedding; required for production retrieval | **INSTALLED** in `models/bge-large-en-v1.5/` (v1.3); dimension=1024 verified |
| `BAAI/bge-m3` model weights | Multilingual alternative | Not yet downloaded |
| `BAAI/bge-reranker-large` model weights | Cross-encoder reranking | Not yet downloaded |
| `chromadb` Python package | Persistent vector store | **INSTALLED** v1.5.9 (v1.3) |
| `sentence-transformers` Python package | Model loading | **INSTALLED** (v1.3) |
| Expert gold labels | Validated evaluation | Member 5 must supply `GoldQuery` set |
| WHO monograph PDFs | Pharmacopoeial retrieval | DNS blocked in container; download manually and place in `pharmacopoeia/incoming/` |
| BP/EP/Ph.Int licensed PDFs | Pharmacopoeial retrieval | Requires institutional licence |

---

## 2. System Limitations

| Limitation | Impact | Mitigation |
|------------|--------|-----------|
| Hash-demo embeddings (not real BGE) | Semantic similarity is approximate | Use BM25/hybrid; plan BGE when model available |
| SQLite preview index (not ChromaDB) | No ANN search; linear scan | Acceptable for ≤2000 chunks; scale to Chroma when ready |
| Researcher-authored probes only | Benchmark not expert-validated | Explicitly labelled in all reports; awaiting M5 |
| SAHPRA PEM-02 version flag | Internal version discrepancy (v8 cover vs v9 content) | Mandatory human review before citing in regulatory decisions |
| ICH Q6B biologics scope | May not apply to small molecules | Product-scope filter must be applied |
| DNS-blocked container | Cannot download WHO monographs | Supply PDFs manually |
| No production security hardening | Research environment only | M1 must add auth, rate limiting and audit before production |
| No PII handling | N/A for drug substance module | Not a limitation for this scope |

---

## 3. Architecture Limitations

| Limitation | Notes |
|------------|-------|
| Inter-member communication uses mock adapters | Live M1/M3/M4/M5 integration not tested |
| LangGraph compatibility is interface-only | Full graph execution not tested end-to-end |
| Ollama LLM is optional | Gap analysis narrative not available without local Ollama server |
| No load testing | REST service not tested under concurrent load |
| No retry/circuit breaker | Network errors propagate to caller |

---

## 4. Data Limitations

- **15 regulatory sources** — may not cover all applicable guidance for complex submissions
- **554 chunks** — small corpus; recall may be low for niche topics
- **No pharmacopoeial monographs** — compendial standards not yet in retrieval pool
- **No sponsor dossier corpus** — M2 only receives sponsor chunks per-call; no cross-case memory

---

## 5. Researcher Attestation

All evaluation results in this package are from researcher-authored navigation probes.
No result is claimed as equivalent to expert-validated regulatory performance.
The phrase "expert-labelled evaluation" is reserved for results obtained using M5-supplied gold queries reviewed by qualified pharmaceutical regulatory assessors.
