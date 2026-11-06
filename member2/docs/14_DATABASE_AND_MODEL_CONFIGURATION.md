# Database and Model Configuration
**Version:** 1.2 | **Date:** 2026-10-28

---

## 1. Current Storage Backend (Offline)

**Type:** SQLite + hash-demo embeddings  
**Location:** `artifacts/real_corpus/`  
**Files:**
- `REGULATORY_CHUNKS.jsonl` — 554 chunks (UTF-8, one JSON per line)
- `REAL_CORPUS_MANIFEST.json` — source manifest with SHA-256 hashes
- `REGULATORY_CHUNK_INDEX.db` — SQLite index

No model download required.

---

## 2. Target Storage Backend (Real BGE)

**Type:** ChromaDB persistent collection  
**Location:** `local_indexes/`  
**Model:** `BAAI/bge-large-en-v1.5` (download ~1.3 GB)

### Setup

```powershell
# Set model cache to project directory
$env:HF_HOME = "C:\...\SAHPRA_Member2_TokenSafe_CitationValidated_v1.1\models"
$env:TRANSFORMERS_CACHE = "$env:HF_HOME"

# Install dependencies
python -m pip install -e ".[vector,models]"

# Build ChromaDB collection
python scripts/build_real_chroma_on_user_pc.py

# Verify
python -c "
import chromadb
client = chromadb.PersistentClient('local_indexes')
col = client.get_collection('sahpra_m2_regulatory')
print(f'Collection: {col.count()} chunks')
"
```

---

## 3. Source Registry

**Location:** `local_indexes/registry.json`  
**Format:** JSON array of `SourceRecord` objects  
**Rebuild:**
```python
from m2.registry import SourceRegistry
reg = SourceRegistry.load('local_indexes/registry.json')
```

---

## 4. Pharmacopoeial Catalogue

**Location:** `pharmacopoeia/phint_catalogue_v0.7.json`  
**Environment variable:** `M2_PHINT_CATALOGUE`

---

## 5. Supported Embedding Models

| Model | Size | Status | Notes |
|-------|------|--------|-------|
| Hash-demo (internal) | 0 MB | Available | Not for production |
| `BAAI/bge-large-en-v1.5` | ~1.3 GB | Blocked (not downloaded) | Preferred |
| `BAAI/bge-m3` | ~2.5 GB | Blocked | Multilingual |
| `sentence-transformers/all-MiniLM-L6-v2` | ~90 MB | Blocked | Lightweight alternative |

---

## 6. ChromaDB Collection Schema

```
collection name: sahpra_m2_regulatory
documents: chunk text
ids: chunk_id (SHA-256-based stable ID)
metadatas:
  source_id: str
  section: str
  page: int | null
  authority: str
  document_code: str
  version: str
  approved: bool
  provenance_verified: bool
```

---

## 7. Reranker Model

**Model:** `BAAI/bge-reranker-large`  
**Status:** Blocked (not downloaded)  
**Usage:**
```python
from m2.retrieval import CrossEncoderReranker
reranker = CrossEncoderReranker("BAAI/bge-reranker-large", local_files_only=False)
service = EvidenceService(store, registry, reranker=reranker)
```
