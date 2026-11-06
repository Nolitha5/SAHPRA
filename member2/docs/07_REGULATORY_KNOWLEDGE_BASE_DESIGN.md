# Regulatory Knowledge Base Design
**Version:** 1.2 | **Date:** 2026-10-28

---

## 1. Source Inventory

The knowledge base contains 15 registered regulatory source documents:

| Authority | Document Code | Title excerpt | Status |
|-----------|--------------|---------------|--------|
| ICH | ICH-M4Q-R1 | ICH M4Q(R1) CTD Quality | Approved |
| ICH | ICH-Q11 | ICH Q11 Drug Substance | Approved |
| WHO | WHO-TRS-1010-A10 | WHO TRS 1010 Annex 10 | Approved |
| ICH | ICH-Q6A | ICH Q6A Specifications | Approved |
| ICH | ICH-Q2R2 | ICH Q2(R2) Validation | Approved |
| ICH | ICH-Q3A-R2 | ICH Q3A(R2) Impurities | Approved |
| ICH | ICH-Q3C-R8 | ICH Q3C(R8) Residual Solvents | Approved |
| ICH | ICH-Q3D-R2 | ICH Q3D(R2) Elemental Impurities | Approved |
| ICH | ICH-Q8R2 | ICH Q8(R2) Pharmaceutical Development | Approved |
| SAHPRA | SAHPRA-PEM-02 | SAHPRA Module 3 Quality Dossier Requirements | Approved (with version flag) |
| ICH | ICH-Q1A-R2 | ICH Q1A(R2) Stability Testing | Approved |
| ICH | ICH-Q1E | ICH Q1E Stability Data Evaluation | Approved |
| ICH | ICH-M7-R2 | ICH M7(R2) Genotoxic Impurities | Approved |
| ICH | ICH-Q6B | ICH Q6B Biotechnology Products | Conditional (biologics scope) |
| EDQM | ICH-Q4B | ICH Q4B Pharmacopoeial Harmonisation | Approved |

**Note:** SAHPRA PEM-02 carries a mandatory version-discrepancy flag (cover says v8; content references v9). ICH Q6B is biologics-only and requires product-scope filter before use.

---

## 2. Chunking Pipeline

Source: `chunking.py` — `section_chunks()`

- **Chunk size:** 512 words (default)
- **Overlap:** 128 words
- **Boundaries:** CTD section headings (`3.2.S.*` pattern) prevent section bleed
- **Stable ID:** SHA-256 of `(source_id, section, page, position, text[:32])`
- **Token safety:** Word-count approximation; real model tokenizer optionally injected
- **Page anchoring:** Every chunk preserves the originating PDF page number

---

## 3. Storage Backends

### 3.1 Current (Offline)
- **SQLite + hash-demo embeddings** in `artifacts/real_corpus/`
- 554 page-anchored chunks from 15 PDFs
- Full SHA-256 verification of source files

### 3.2 Target (Online — User Machine)
- **ChromaDB** persistent collection in `local_indexes/`
- **BGE embeddings** — `BAAI/bge-large-en-v1.5` (1.3 GB download required)
- Collection is reopenable; stable chunk IDs preserved across sessions
- Build script: `scripts/build_real_chroma_on_user_pc.py`

---

## 4. Source Registration Rules

A source is registered via `SourceRegistry.register()`:
1. `source_id` must be globally unique and stable
2. If a source already exists with the same `source_id`, the metadata must match exactly (no silent overwrites)
3. `approved` and `provenance_verified` default to `False` — must be explicitly set to `True` after review
4. `sha256` must match the physical file hash; verified by `citation_audit.py`

---

## 5. Index Integrity

- `validation/v1.1_PAGE_ANCHOR_AUDIT.json` — 554/554 chunks verified
- `SHA256SUMS.txt` — 15 source PDFs hashed
- `regulatory_sources/UNIQUE_PDF_INTEGRITY_MANIFEST_v0.5.json` — full manifest

---

## 6. Rebuild Commands

```powershell
# Offline rebuild (no model download needed)
python scripts/collect_validate_index.py --index

# Real ChromaDB/BGE (internet required, ~1.3 GB download)
python -m pip install -e ".[vector,models]"
python scripts/build_real_chroma_on_user_pc.py

# Verify citation integrity
python -m m2.citation_audit --root .
```
