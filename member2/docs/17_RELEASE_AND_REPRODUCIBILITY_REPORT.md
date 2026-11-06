# Release and Reproducibility Report
**Version:** 1.3 | **Date:** 2026-10-28

---

## 1. Release Package

| Item | Value |
|------|-------|
| Package | `releases/SAHPRA_Member2_KnowledgeBase_Integration_v1.3.1.zip` |
| SHA-256 | See `releases/SAHPRA_Member2_KnowledgeBase_Integration_v1.3.1.zip.sha256` |
| Base version | v1.3 |
| New in v1.2 | DEF-001 Unicode fix + 18 documentation files |
| New in v1.3 | Phase 2 KB integration: 50-file Pharmacy inventory, 45 dossier PDFs copied + hash-verified, 5 HTML quarantined, ChromaDB/BGE index (regulatory + dossier), 22 new tests |
| New in v1.3.1 | Corrected retrieval benchmark (source-level deduplication; prior Recall>1.0 superseded); S.4 evidence smoke test suite (20 tests); corrected source classification (dossier=Class D, separate collection); FINAL_RETRIEVAL_BENCHMARK.json; FINAL_NATIVE_CHROMADB_BGE_REPORT.json; FINAL_REGRESSION_RESULTS.txt; FINAL_SOURCE_AND_CITATION_AUDIT.json; FINAL_MEMBER2_ACCEPTANCE_REPORT.md |

---

## 2. Included in Release

- Complete `src/m2/` Python package (36 modules)
- All `tests/` files (18 test files, 137 tests)
- All `docs/` documentation (18 new + 33 existing)
- All `scripts/` scripts
- Regulatory source manifests (`regulatory_sources/`)
- Validation reports (`validation/`)
- Configuration files (`config/`, `pyproject.toml`)
- Pharmacopoeial catalogue (`pharmacopoeia/` — metadata only, no licensed PDFs)
- Technical preview index (`artifacts/real_corpus/` — SQLite + JSONL)
- Example data (`examples/`)

---

## 3. Excluded from Release

- Virtual environments (`.venv/`)
- Downloaded model weights (`models/`)
- Licensed pharmacopoeial PDF content
- Confidential sponsor dossier data
- Large ChromaDB collections (if present in `local_indexes/`)

---

## 4. Reproduction Steps

```powershell
# 1. Extract release ZIP
Expand-Archive "releases/SAHPRA_Member2_Final_Implementation_v1.2.zip" -DestinationPath ".\extracted\"

# 2. Navigate to project
cd "extracted\SAHPRA_Member2_Final_Implementation_v1.2"

# 3. Install
python -m pip install -e ".[dev]"

# 4. Run tests
python -m pytest tests/ -q
# Expected: 137 passed, 0 failed

# 5. Run offline benchmark
python -m pytest tests/test_technical_benchmark_v06.py -v

# 6. Start REST service (optional)
$env:M2_SERVICE_TOKEN = "test-token-dev"
python -m uvicorn m2.api:router --host 127.0.0.1 --port 8001
```

---

## 5. Version History

| Version | Date | Changes |
|---------|------|---------|
| v0.2 | Oct 2026 | Three user PDFs, SQLite preview |
| v0.3 | Oct 2026 | Real regulatory PDFs indexed |
| v0.4 | Oct 2026 | 15-source catalogue, Chroma script |
| v0.5 | Oct 2026 | All 15 PDFs physically included |
| v0.6 | Oct 2026 | Full S.4 + evaluation framework |
| v0.7 | Oct 2026 | WHO pharmacopoeial catalogue |
| v0.8 | Oct 2026 | WHO acquisition (DNS-blocked gracefully) |
| v0.9 | Oct 2026 | Compendia ingestion governance |
| v1.0 | Oct 2026 | Deferred pharmacopoeial corpus integration |
| v1.1 | Oct 2026 | Token-safe chunking + 554-anchor citation audit |
| v1.2 | Oct 2026 | DEF-001 Unicode fix + full documentation suite |
| v1.3 | Oct 2026 | Phase 2 KB integration: Pharmacy inventory, 45 dossier PDFs, ChromaDB/BGE, 22 new tests |

---

## 6. SHA-256 Verification

```powershell
# Verify the release ZIP itself
python -c "
from m2.registry import file_sha256
print(file_sha256('releases/SAHPRA_Member2_Final_Implementation_v1.2.zip'))
"
# Compare against releases/SAHPRA_Member2_v1.2_SHA256.txt
```
