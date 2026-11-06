# Development runbook — Tier 0 → Tier 3

## Prerequisites

- Team: M1 canonical `Finding` and LangGraph `StateGraph` interface; M3 `DossierChunk` schema and section tag map; M5 expert source approvals; M4 metric/export contracts.
- Machine: Python 3.11/3.12 with venv, local model access; tests may run on 3.13, model wheels may vary.
- Source permissions: reviewed regulatory PDFs, authoritative URLs/editions/versions, approved local storage. No copyrighted originals included in ZIP.
- Git: one team-owned shared mono-repo (M1 owner), Member-2 feature branch. M1 approves merges; do not overwrite teammates' files.

## Tier 0 — real cited end-to-end thread

1. Install package in M1's development environment: `pip install -e ".[vector,models,dev]"`.
2. Have M3 emit real clean, section-aware dossier JSON. Confirm section/page identities.
3. Have M5 approve at least one ICH source/version and verify its PDF hash and authorized storage.
4. `register-source` and `ingest-pdf` in `research` config. This creates a Chroma collection isolated by embedding model and dimension.
5. Use `EvidenceService.retrieve()` from M1 S.1 node; verify passage text matches original guideline document and its page/section locator.
6. Route one finding to M5 stub QA and human UI; let M4 audit persist the result. Record actual evidence, timestamps and CLI logs.
7. Test a deliberately unanswerable question; verify `INSUFFICIENT_EVIDENCE`, no invented passage and human-review flag.

**Tier-0 success must be observed in the shared app.** Current synthetic tests confirm interfaces only, not real-world pass.

## Tier 1 — all Member-2 functional code

- Approve indexed source manifest (see `SOURCE_POLICY.md`), including correct edition windows.
- Agree and implement M3 chunk/table format, then test OCR/structure on real samples. M3 remains the extractor owner.
- Integrate RERA as the only regulatory search service for all seven specialist agents and M5 QA.
- Complete S.4 sections 4.1–4.5, structured tables, cautious numerical comparisons and source-grounded findings.
- If agentic text analysis is desired, enable local Ollama with quoted evidence gates; record failures explicitly. Model output is never a regulatory authority.
- Validate M1's Pydantic Finding adapter and M4/M5 interfaces. Do not duplicate their memory or UI.
- Log all data-version/config decisions; continue weekly clean merges.

## Tier 2 — controlled performance evidence

- M5 provides an expert-labelled set of queries, relevance anchors, correctness rubric and negative/ambiguous examples.
- Freeze source corpus hashes, fixed actual tokenizer and an evaluation run plan. Do not compare incompatible source corpora.
- Run no-rerank and rerank grid; store model/size/overlap results, latency/hardware notes, source hashes, experiment IDs and error categories. Only select a best configuration from verified results.
- M4 runs the entire A/B/C/D comparison with human-grounded findings; M2 sends retrieval outputs, query labels and per-run metrics. Ragas faithfulness evaluations require M4/M5's defined procedure and model judge; JSON metrics here do **not** claim faithfulness results.
- M5 participates in source, citation and S.4 finding audits. Measure false negatives and issues requiring human review.
- Document limitations including partial source coverage, model weaknesses, OCR failures, thresholds and hardware resource needs.

## Tier 3 — explicitly deferred

Full-system document calls for controlled learning/advanced actuators only after the core app is stable and governance approved. The Member-2 requirements do not assign unrestricted online self-training or autonomous regulatory action; this package intentionally has none. Treat new automated feedback and actors as a separately reviewed change request.

## When the group changes a decision

1. Record change in `PROVISIONAL_DECISIONS.md` with new owner and date.
2. Update Pydantic adapter or configuration first; maintain compatibility or use semantic contract version.
3. Add a regression test reproducing the change; re-run pytest and a Tier-0 end-to-end scenario.
4. Rerun expert retrieval experiments after tokenizer, embedding, corpus or reranker changes; old benchmarks may no longer compare.
5. Submit PR for M1's merge only with evidence. M1 does final application assembly.

## Windows setup detail

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pytest -q
python -m m2.cli demo

# Once the approved corpus, optional dependencies and configuration exist:
python -m pip install -e ".[vector,models,dev]"
Copy-Item config\production.template.json config\local.json
$env:M2_SERVICE_TOKEN = 'replace-with-long-secret-from-team-secret-manager'
$env:M2_STARTUP_CONFIG = 'config/local.json'
uvicorn m2.api:app --host 127.0.0.1 --port 8012
```

Never commit tokens, credentials, confidential case material, regulator PDFs with restricted rights, or downloaded model cache files. Local registry/index paths are `.gitignore`d.
