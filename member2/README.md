# SAHPRA Agentic QA-RAG — Member 2: Regulatory Knowledge Base

> **This system is a regulatory assessment research prototype.**
> It does not independently authorise or reject medicines.
> All outputs require review by a qualified human assessor before any regulatory decision is made.

## 1. What Member 2 Is

Member 2 is the **Regulatory Knowledge Base and Evidence Retrieval** subsystem of the SAHPRA Agentic QA-RAG system. It provides authoritative regulatory evidence in response to queries from other members of the multi-agent pipeline, specifically to support the assessment of pharmaceutical manufacturing dossiers (CTD Module 3, Section S.4 — Drug Substance Control).

It operates entirely on-premises, never calls external LLM APIs, and enforces strict source isolation between approved regulatory guidance, sponsor dossier material, and quarantined compendial sources.

## 2. Agents Implemented

| Agent | Module | Role |
|---|---|---|
| **RERA** (Regulatory Evidence Retrieval Agent) | `src/m2/retrieval.py`, `src/m2/runtime.py` | Embeds queries with BAAI/bge-large-en-v1.5, retrieves ranked evidence from ChromaDB |
| **S.4 Control Agent** | `src/m2/s4.py`, `src/m2/s4_rules.py` | Maps S.4.x questions to regulatory evidence; dual-panel dossier vs. regulatory |
| **Source Governance** | `src/m2/registry.py`, `src/m2/label_governance.py` | Enforces source classification (A/B/C/D) and citation provenance |
| **Citation Audit** | `src/m2/citation_audit.py` | Validates every evidence chunk to its declared source |
| **KB Explorer** | `tools/member2_explorer/app.py` | Streamlit diagnostic UI for local researchers |

## 3. Relationship to the Full SAHPRA Architecture

```
Member 1 (Dossier Ingestion)
    ↓ structured dossier sections
Member 2 (Regulatory Knowledge Base) ← this repository
    ↓ evidence chunks + citation IDs
Member 3 (Gaps & Deficiency Analysis)
    ↓ deficiency list
Member 4 (Report Generation)
    ↓ draft assessment
Member 5 (Human Assessor Review)
```

Member 2 receives substance/section queries from Members 1 and 3 via its FastAPI service (`src/m2/api.py`) and returns ranked regulatory evidence with provenance metadata. It does not make approval or rejection decisions.

## 4. Technologies

| Component | Technology |
|---|---|
| Embeddings | BAAI/bge-large-en-v1.5 (1024-dim, local cache) |
| Vector store | ChromaDB 1.5.x (persistent, local only) |
| Chunking | Token-safe page-anchored chunking (`src/m2/chunking.py`) |
| API | FastAPI + Pydantic (`src/m2/api.py`) |
| LangGraph adapter | `src/m2/langchain_adapter.py` |
| Explorer UI | Streamlit 1.66+ (`tools/member2_explorer/app.py`) |
| Testing | pytest 186 passing |
| Package | `pyproject.toml` (hatchling) |

## 5. Source-Code Structure

```
member2/
├── src/m2/                    # Core Python package
│   ├── api.py                 # FastAPI service endpoints
│   ├── retrieval.py           # BGE + ChromaDB retrieval
│   ├── runtime.py             # M2Runtime: main entry point
│   ├── s4.py                  # S.4 Control Agent
│   ├── s4_rules.py            # S.4 section-to-ICH mapping rules
│   ├── registry.py            # Source registry and classification
│   ├── embeddings.py          # SentenceTransformerEmbedder wrapper
│   ├── chunking.py            # Token-safe regulatory chunking
│   ├── token_safe_index.py    # Fast-tokenizer aligned indexing
│   ├── citation_audit.py      # Chunk-to-source citation validation
│   ├── label_governance.py    # Approval / classification labels
│   ├── schemas.py             # Pydantic data models
│   ├── storage.py             # ChromaDB collection management
│   ├── langchain_adapter.py   # LangGraph / LangChain integration
│   ├── integration.py         # M1-M5 contract implementations
│   ├── readiness.py           # Pre-flight checks
│   └── ...                    # Additional support modules
├── tests/                     # pytest test suite (186 passing)
├── scripts/                   # Indexing, validation, audit scripts
├── tools/member2_explorer/    # Streamlit Knowledge Base Explorer
│   └── app.py
├── config/                    # Runtime configuration templates
│   ├── default.json           # Demo/memory mode
│   └── production.template.json  # ChromaDB + BGE template
├── docs/                      # Architecture and operations documentation
├── examples/                  # Synthetic test fixtures (clearly labelled)
├── validation/                # Test results and audit reports
├── pyproject.toml             # Package configuration
└── README.md                  # This file
```

## 6. Installation Requirements

```bash
# Python 3.11+ required (developed on 3.13.2)
pip install -e ".[dev]"
```

**Key dependencies** (from `pyproject.toml`):
- `chromadb>=1.5`
- `sentence-transformers>=3.0`
- `fastapi`, `uvicorn`
- `streamlit>=1.60`
- `pydantic>=2`

**Local model** — download separately (not included in this repository):
- `BAAI/bge-large-en-v1.5` — place in `models/bge-large-en-v1.5/` or configure `HF_HOME`

## 7. How to Build the Local Knowledge Base

> The ChromaDB collections and pharmaceutical source PDFs are **not** included in this repository. The following steps reproduce them from authorised sources.

```bash
# Step 1: Obtain regulatory source PDFs
# Place ICH, WHO, EMA, FDA guidances in regulatory_sources/
# (see docs/08_SOURCE_GOVERNANCE_AND_PROVENANCE.md for the authorised list)

# Step 2: Run the regulatory indexing script
python scripts/build_real_chroma_on_user_pc.py

# Step 3: (Optional) Index sponsor dossier material
# Place sponsor PDFs in pharmacopoeia/incoming/raw_from_pharmacy/
python scripts/build_dossier_chroma.py

# Step 4: Build the coverage audit
python scripts/build_complete_audit.py
```

Expected result: ChromaDB regulatory collection with 554 chunks (15 sources) at `local_indexes/regulatory_chroma/`.

See `docs/14_DATABASE_AND_MODEL_CONFIGURATION.md` for ChromaDB collection naming and BGE cache configuration.

## 8. How to Launch the Streamlit Explorer

```powershell
# Windows PowerShell (recommended)
.\scripts\start_member2_explorer.ps1

# Or directly
python -m streamlit run tools/member2_explorer/app.py --server.address 127.0.0.1 --server.port 8501
```

Open `http://127.0.0.1:8501` in a browser. The app binds to localhost only and does not send data externally. See `docs/19_VISUAL_EXPLORER_USER_GUIDE.md` for a full page-by-page guide.

## 9. How to Run the Automated Tests

```bash
# Full suite (186 tests)
pytest

# Fast subset (skips slow BGE / ChromaDB tests)
pytest -m "not slow"

# With coverage
pytest --cov=src/m2
```

The test suite uses synthetic fixtures only. It does not require the BGE model or ChromaDB to pass in demo mode.

## 10. How Other Members Integrate with RERA and S.4

Member 2 exposes a FastAPI service:

```python
# Start the service (set M2_SERVICE_TOKEN env var first)
uvicorn m2.api:app --host 127.0.0.1 --port 8000
```

**Primary endpoints:**

| Endpoint | Description |
|---|---|
| `POST /rera/query` | Retrieve ranked regulatory evidence |
| `POST /s4/assess` | S.4 dual-panel assessment (regulatory + dossier) |
| `GET /health` | Service readiness check |

For programmatic integration, use the LangGraph adapter:

```python
from m2.langchain_adapter import M2LangGraphNode
from m2.runtime import M2Runtime

runtime = M2Runtime.from_config("config/production.template.json")
node = M2LangGraphNode(runtime)
# node is a Runnable compatible with LangGraph StateGraph
```

See `docs/06_M1_M3_M4_M5_INTEGRATION_CONTRACTS.md` for full data contracts and message schemas.

## 11. Present Technical Status and Remaining Limitations

### Validated (v1.4.0)

- 186 pytest tests passing
- ChromaDB regulatory collection: 554 chunks, 15 ICH/WHO/EMA sources
- BGE retrieval confirmed with real embeddings (cosine similarity)
- Source isolation verified: 0 dossier chunks in regulatory collection
- S.4 dual-panel assessment with mandatory human-review flag
- Streamlit Knowledge Base Explorer demonstrated live
- FastAPI service with token-based authentication

### Known Limitations and Outstanding Requirements

| Requirement | Status |
|---|---|
| Expert-labelled relevance evaluation | Not completed — requires SAHPRA assessor annotations |
| M1-M5 live integration test | Not completed — Members 1/3/4/5 not yet connected |
| Compendial monographs (BP/Ph.Eur.) | Quarantined — redistribution rights not confirmed |
| IPRP QWGG DS guidance | Not indexed — PDF not yet obtained |
| Scanned amlodipine PDFs (2 files) | 0 chunks — image-only, no extractable text |
| Human assessor pilot | Not started |
| BGE vs. bge-m3 / MiniLM comparison | Not conducted |
| Authorised regulatory approval of any source document | Not granted |

See `docs/16_KNOWN_LIMITATIONS_AND_DEPENDENCIES.md` and `docs/12_FINAL_ACCEPTANCE_CHECKLIST.md` for the full acceptance status.

---

**Repository:** https://github.com/Nolitha5/SAHPRA  
**Branch:** aziz-and-sipho  
**Team:** Aziz & Sipho  
**Version:** v1.4.0
