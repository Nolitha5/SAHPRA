# Claude continuation instructions — reviewed pharmacopoeia added later

Work only within the user's extracted Member 2 project and follow the team's
approved repo/branch when supplied. Do not edit Members 1, 3, 4 or 5 modules or
claim their live integration based on stubs. Read README.md and the v1.0 handoff
report first. Preserve all 15 guideline PDFs, hashes, RERA, S.4, audit interfaces,
security checks and quarantine isolation.

**Before writing production data:** examine every additional reference's official
publisher, edition, effective date, scope, identity, SHA-256 and permitted local AI
indexing. Never silently promote `artifacts/quarantine/compendial_discovery.sqlite3`
into the regulatory evidence DB. Research-lead FTS results are not citations.
If a source's rights, edition or product applicability is unresolved, leave it
quarantined and record the reason. Do not assume BP, USP, Ph. Eur., IP and WHO
standards are interchangeable or automatically applicable to SAHPRA decisions.

Use `scripts/stage_reviewed_monograph.py` for checked-source intake (it never
self-approves). Implement a separate authorised indexed-source release only upon
M5 review and actual rights/adoption evidence; version each source and index
with original page anchors. For WHO-specific material, reuse the existing guarded
`import_verified_monograph` logic and validate its assumptions. If any new
compendia type differs, add a separate adapter and tests rather than weakening
WHO identity checks.

Use true ChromaDB+BGE and repeatable model-token-aware chunking on a compatible
machine. Compare against the existing engineering baselines but never conflate
hash embeddings with BGE or researcher-written navigation probes with expert
labels. Validate native persistence, mixed metadata filters, abstention and
citation reconstruction. Collect M5-labelled S.4/S.5 examples and issue a
signed report to M4's harness. Keep M1 human gate and M5 QA statuses pending
until human decisions are recorded. Preserve negative cases and rerun full tests.

**Output:** tagged version increment, diff/changelog, corpus + rights inventory,
model version/hash and index manifest, experimental protocol/results, redacted
logs, validation/limitations report, runnable ZIP and integration handoff.
Never report regulatory approval or pilot completion without real evidence.
