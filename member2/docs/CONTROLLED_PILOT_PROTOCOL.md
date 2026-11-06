# Controlled regulatory research pilot — protocol and stop/go criteria

**STATUS: NOT AUTHORISED OR CONDUCTED.** This document prepares the research team to conduct a pilot; synthetic test cases produced by the package are not genuine human-assisted regulatory pilot observations.

## Required approvals and independent validation
1. Research protocol/supervisor authorisation; required ethics/institutional approvals and applicable SAHPRA permissions.
2. Privacy/confidentiality review, lawful handling of sponsor dossiers, secure local machine setup and authorised assessor accounts.
3. Version-locked approved regulatory corpus, provenance, source licences, actual embeddings and native ChromaDB persistence test with positive/negative retrieval.
4. Actual M1–M5 integrated release, reproducible tests, audited human gate, no autonomous regulatory decisions.
5. M5-approved expert ground truth and an M4 executed A/B/C/D comparison with controls and predefined endpoints.
6. Agreed pilot enrolment, training, SOPs, inclusion/exclusion criteria, escalation and stop rules.

## Study design (proposal, requires research approval)
- **Setting:** Controlled research setting with local/offline approved data handling.
- **Inputs:** De-identified or authorised retrospective/synthetic study dossiers, selected and labelled according to the approved research protocol.
- **Comparison:** Human-only vs human-assisted review, randomized or counterbalanced case order where appropriate; comparative A–D system tests belong to M4.
- **Endpoints:** Retrieval Precision@K, Recall@K, MRR/nDCG; S.4 finding precision/recall/F1, unsupported-claim rates, citation validity, missed-deficiency rate, reviewer time and workload, assessor trust/usability (measured, not assumed).
- **Human authority:** An authorised assessor must make each decision; generated findings remain provisional, flags visible and decision provenance auditable.
- **Governance:** No live regulatory approval, adverse regulatory communication, continuous online learning or automated actuator output during the research pilot without separate approval.

## Safety stop conditions
Stop a pilot run and escalate to the human supervisor if: actual source pages/editions cannot be verified, a citation is fabricated or points to another guideline, sponsor information is disclosed outside an approved role/case, a human decision is preselected, audit events are missing, the local runtime uses an unapproved external endpoint, or an unreviewed finding reaches the decision gate. Document the incident, the case, source versions, and remediation before resuming.

## Required artifacts
- `pilot_evidence/pilot_authorisation.json`: formal approvals, authorised personnel, signed protocol IDs/dates and data-use scope.
- `pilot_evidence/assessor_pilot_results.json`: de-identified participant/case/run IDs, randomization or case ordering, comparison arm, reviewed findings, time/workload, human dispositions and valid provenance.
- M4's locked A–D evaluation exports and complete error analysis.
- M5's verified rubric, domain judgments and human-assisted evaluation records.
- M1 full-system runtime trace and durable M4 audit record for each case.
- Final methodological report: limitations, source coverage, latency, hardware, evidence sufficiency, negative cases and ethical constraints.

## Synthetic workflow delivered here
`python -m m2.team_simulation --root . --out artifacts/synthetic_team_simulation`

This tests only (1) the M1 state adapter interface, (2) a M3 synthetic JSON handoff, (3) actual M2 retrieval/S.4, (4) simulated SQLite M4 audit, (5) simulated M5 required-field QA, and (6) an explicit simulated human gate. It generates `synthetic_integration_report.json`, `synthetic_audit_events.json`, and `synthetic_case_audit.sqlite3`. **It provides no assessor opinion and no regulatory outcome.**

## Gate to claim pilot completion
A pilot is complete only after authentic approvals, real approved trial execution and signed M4/M5/M1 evidence are available and audited. The machine-readiness report (`python -m m2.readiness`) is only an evidence-presence checklist, not a regulatory certificate.
