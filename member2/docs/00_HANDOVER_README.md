# Member 2 Handover — SAHPRA Agentic QA-RAG
**Version:** 1.2  
**Date:** 2026-10-28  
**Member:** 2 — Evidence/RERA, Regulatory Knowledge Base, S.4 Control

---

## Quick Start

```powershell
# Install (dev dependencies only — no model weights required)
python -m pip install -e ".[dev]"

# Run all tests
python -m pytest -q

# Start the REST service (research mode)
set M2_SERVICE_TOKEN=<your-token>
python -m uvicorn m2.api:router --host 127.0.0.1 --port 8001
```

## What Is Implemented

Member 2 provides three core subsystems accessible via REST, Python function call or LangGraph node:

1. **Evidence/RERA Agent** — retrieves regulatory evidence from an approved source registry.
2. **S.4 Control Agent** — produces provisional structured findings for CTD 3.2.S.4.1–3.2.S.4.5.
3. **Regulatory Knowledge Base** — manages source registration, chunking, provenance and retrieval.

All subsystems are implemented, tested and packaged. See [docs/IMPLEMENTATION_GAP_ANALYSIS.md](IMPLEMENTATION_GAP_ANALYSIS.md) for full feature status.

## What Is NOT Implemented / Blocked

- **Real ChromaDB/BGE vector index** — model weights not downloaded in this environment. Run `python scripts/build_real_chroma_on_user_pc.py` on an internet-connected machine after `pip install -e ".[vector,models]"`.
- **Expert-labelled evaluation** — requires Member 5 gold labels.
- **Licensed pharmacopoeial PDFs** — require institutional licence. Place in `pharmacopoeia/incoming/`.

## Key File Locations

| Artefact | Path |
|----------|------|
| Source code | `src/m2/` |
| Tests | `tests/` |
| Regulatory PDFs | `regulatory_sources/` |
| Technical documentation | `docs/` |
| Validation reports | `validation/` |
| SQLite/hash preview index | `artifacts/real_corpus/` |
| Pharmacopoeial catalogue | `pharmacopoeia/` |
| Release packages | `releases/` |

## Safety Constraints

- No autonomous regulatory approval, rejection or authorisation is produced.
- Every finding is marked `requires_human_review=True`.
- Numerical comparisons use only sponsor-submitted values; no invented thresholds.
- Sources must be `approved=True` and `provenance_verified=True` to enter retrieval.

---

*See [docs/13_CLAUDE_IMPLEMENTATION_REPORT.md](13_CLAUDE_IMPLEMENTATION_REPORT.md) for the full implementation summary.*
