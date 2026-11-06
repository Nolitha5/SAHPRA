# Member 2 research completion matrix — version 0.2

| Requested milestone | Code delivered | What was actually executed in this environment | External blocker | Status |
| --- | --- | --- | --- | --- |
| Native ChromaDB runtime | Persistent Chroma adapter and isolated native persistence test | Attempted `pip install chromadb`; DNS unavailable. Test returns BLOCKED, never PASS | Internet-connected Python environment and installed ChromaDB | **BLOCKED** |
| Actual SAHPRA/ICH/WHO source indexing | Official publisher catalogue, secure acquisition, SHA256/PDF checks, manual curation, ingestion/index CLI | Verified official source links via public source pages; direct SAHPRA PDF acquisition attempt failed. No official PDF indexed. | Real PDF downloads, source permissions/edition review and local model | **NOT RUN** |
| Expert-labelled evaluation | Anchor-based retrieval scorer, model/chunk/reranker grid, ground-truth import and provenance checks | Previous synthetic benchmark only; no expert-labelled or adjudicated dataset supplied | M5 expert reviewers, approved labels and real corpus | **NOT RUN** |
| M1–M5 integration | M1 LangGraph adapters, M3 chunk contract, M4 export, M5 QA schema and a 5-member contract simulation | Actual M2 code + **simulator stubs** M1/M3/M4/M5, with SQLite event log and explicit synthetic human gate | Real member code, shared repo, team agreed contracts | **SIMULATED, NOT LIVE** |
| Controlled regulatory pilot | Pilot protocol, ethics/privacy/stop conditions, readiness matrix, simulated flow evidence | Synthetic engineering run; no real assessors, protected dossiers, scientific QA, approved trial or pilot outcomes | Institutional and SAHPRA approvals, real assessor study | **NOT AUTHORISED / NOT RUN** |
| Additional engineering verification | Source gating, persistent SQLite fallback, label governance, API/adapter tests | All tests in `validation/PYTEST_FULL_RUN.txt`, fallback SQLite persistence, simulation audit | None for synthetic engineering scope | **PASS** |

**No evidence of deployment-ready or regulatory-valid scientific performance is claimed.** Original v0.1 synthetic artifacts are retained for reproducibility and clearly marked synthetic. This v0.2 release is an extended development/verification package, not a completed SAHPRA study.
