# 19. Member 2 Visual Explorer — User Guide
**Version:** v1.4.0  
**Date:** 2026-10-29

---

## What This Tool Is

The **Member 2 — Regulatory Knowledge Base & Evidence Explorer** is a local, read-only developer and researcher diagnostic interface for the SAHPRA Agentic QA-RAG Member 2 system.

It is **not** the Member 5 authorised assessor UI.  
It does **not** send queries to external LLM APIs.  
It does **not** modify any vector collection or source document.  
It runs on `127.0.0.1` only and is never accessible over the network.

---

## Prerequisites

- Python 3.13 (or compatible)
- Packages: `streamlit>=1.60`, `chromadb>=0.5,<2`, `sentence-transformers>=3.0`
- BGE model cached under `models/bge-large-en-v1.5/`
- ChromaDB indexes in `local_indexes/regulatory_chroma/` and `local_indexes/dossier_chroma/`
- Audit CSV/JSON in `validation/` (run `scripts/build_complete_audit.py` first if absent)

### Install missing packages

```bash
pip install streamlit chromadb sentence-transformers
```

---

## Launching the Application

### Option A — PowerShell launcher (recommended)

```powershell
.\scripts\start_member2_explorer.ps1
```

Or with a custom port:

```powershell
.\scripts\start_member2_explorer.ps1 -Port 8502
```

### Option B — Direct command

```bash
python -m streamlit run tools/member2_explorer/app.py --server.address 127.0.0.1 --server.port 8501
```

### Access

Open your browser at: **http://127.0.0.1:8501**

---

## Pages

### A — System Overview
Displays live database connection status, chunk counts, source counts, and quarantine statistics read directly from ChromaDB collections and project manifest files.

### B — Knowledge Base Browser
Browse indexed regulatory and dossier sources filtered by substance, source ID, or filename.  
- **Regulatory tab** (Class A): shows source metadata, SHA-256, page count, sample passages  
- **Dossier tab** (Class D): shows per-substance document inventory and chunk counts  
- **Quarantined tab** (Class C): metadata-only view; content suppressed  

### C — Regulatory Evidence Search
Submit a natural language research question. Retrieval uses real BAAI/bge-large-en-v1.5 embeddings and the native ChromaDB regulatory collection.

- No external LLM API calls
- Results show source authority, title, section, page, citation ID, retrieval score
- Displays "Insufficient evidence" when no relevant passages are found
- All results marked UNAPPROVED_TECHNICAL_ONLY

### D — S.4 Control Demonstration
Select a substance (Valsartan, Amlodipine, Hydrochlorothiazide) and an S.4 section (S.4.1–S.4.5).  
Runs the BGE retrieval against both the regulatory and dossier collections simultaneously.  
Displays each in a separate panel with appropriate classification labels.  
Outputs a provisional QA status block with a mandatory human-review notice.

### E — Database Completeness
Source coverage table: source → extraction → classification → indexing → verification.  
Explains all discrepancies (zero-chunk PDFs, not-indexed IPRP guidance, quarantined compendial collection).  
Provides CSV and JSON export within the project folder.

### F — Tests & Benchmarks
Historical test outcomes and retrieval benchmark metrics from v1.3.1 validation.  
Clearly separates historical results from current session.  
Shows what is and is not expert-validated.

---

## BGE Model Load Time

The first search after app launch takes approximately 20–40 seconds while the 1.3 GB BGE model loads into memory. Subsequent queries within the same session are fast (typically < 1 second).

---

## Security Notes

- The app binds to `127.0.0.1` only via `--server.address 127.0.0.1`
- Telemetry disabled via `--browser.gatherUsageStats false`
- Dossier content is displayed with access restriction labels
- No data is sent to external services

---

## Rebuild Prerequisites

If ChromaDB indexes are absent (e.g. fresh checkout):

```bash
python scripts/build_real_chroma.py          # regulatory: 554 chunks
python scripts/build_dossier_chroma.py       # dossier: 2064 chunks (~20 min)
python scripts/build_complete_audit.py       # coverage CSV/JSON
```

Then launch the explorer.
