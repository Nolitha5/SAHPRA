# Advanced release validation report — 15 October 2026 (v0.2)

## Executed locally
- `PYTHONPATH=src python -m pytest -q`: **52 passed**. Tests include original 39 plus official catalogue/acquisition security, labels gate, native Chroma block reporting, five-member contract simulation, synthetic QA, SQLite vector persistence and research-mode fallback rejection.
- `PYTHONPATH=src python scripts/validate_local_release.py`: **PASS** for unit/contract checks, **BLOCKED** for native ChromaDB, and **NOT READY** for authorised regulatory pilot.
- `PYTHONPATH=src python -m m2.team_simulation`: synthetic M1/M3/M4/M5 interface stubs with real M2 Evidence/RERA and S.4 output; persistent SQLite audit written. Not a genuine team integration.
- Genuine SQLite vector persistence: reopen after connection closure passed. SQLite is an **offline engineering fallback only**, not equivalent to ChromaDB.
- Native `pip install chromadb`: attempted but package-index DNS resolution failed. Native ChromaDB was not run. Published source URLs were checked, but direct PDF acquisition failed; no real guidelines indexed.

## Not demonstrated
- Native ChromaDB installation, persistence and actual BGE embedding/reranking, and index memory/latency on the target machine.
- Fully acquired, hashed, domain-approved regulatory corpus with verified page/section citations.
- Expert-labelled or independently adjudicated retrieval/gap evaluation and A–D comparison.
- Real integration with Members 1, 3, 4, 5, their source code and human UI.
- Regulatory research pilot approval, enrolled qualified assessors, real controlled case results, full-system feasibility or SAHPRA deployment.

## Machine-readable evidence
- `validation/ADVANCED_VALIDATION_REPORT.json`
- `validation/PYTEST_FULL_RUN.txt`
- `validation/CHROMA_RUNTIME_CHECK.json`
- `validation/RESEARCH_AND_PILOT_READINESS.json`
- `artifacts/synthetic_team_simulation/synthetic_integration_report.json`
- `artifacts/synthetic_team_simulation/synthetic_audit_events.json`

**Interpretation:** substantial source implementation, executable synthetic engineering tests, and a prepared regulatory research workflow; *not* regulatory or study completion. `docs/RELEASE_STATUS_v0.2.md` is authoritative for pending external milestones.
