# Security and Human Review Policy
**Version:** 1.2 | **Date:** 2026-10-28

---

## 1. Regulatory Safety Constraints

Member 2 is implemented with the following mandatory safety constraints:

1. **No autonomous regulatory decision.** The system does not approve, reject or authorise pharmaceutical medicines or submissions.
2. **Human review always required.** Every `Finding` has `requires_human_review=True`. This field is set unconditionally in `S4ControlAgent.review()` and cannot be overridden by agent logic.
3. **No invented thresholds.** Numerical comparisons use only sponsor-submitted values. No regulatory threshold is fabricated. `s4_rules.compare_sponsor_batch_data()` only compares values against limits stated in the dossier itself.
4. **Source provenance enforced.** Only sources with `approved=True` and `provenance_verified=True` participate in regulatory retrieval.
5. **QA handoff.** All findings arrive at M4 with `qa_status=PENDING`. The status can only be changed by M4/human review, not by M2.

---

## 2. API Security

- The `/m2` router requires a `X-M2-Token` header matching `M2_SERVICE_TOKEN`.
- Token comparison uses `secrets.compare_digest()` to prevent timing attacks.
- `M2_SERVICE_TOKEN` must be set as an environment variable before service startup; the server refuses to start in research mode without it.
- No secrets are logged or returned in API responses.

---

## 3. LLM Safety

- The Ollama LLM client is optional. If unavailable, deterministic rationale is used.
- LLM-generated narrative is labelled in `attributes.llm_gap_analysis` and does not change `status` or `qa_status`.
- The LLM prompt explicitly instructs the model not to invent regulatory requirements.
- LLM outputs are never inserted into `regulatory_evidence`; only retrieved passages from registered sources appear there.

---

## 4. Data Handling

- Source PDFs are not distributed to external APIs.
- Sponsor dossier text is not sent to external services (LLM calls use locally hosted Ollama).
- Pharmacopoeial licensed content is not included in release packages.
- No PII is processed by Member 2.

---

## 5. Human Review Requirements

The following actions require human sign-off and cannot be automated:

| Action | Reason |
|--------|--------|
| Promoting a source from quarantine to approved | Regulatory integrity |
| Changing `qa_status` from PENDING | Assessment decision |
| Marking a finding as compliant or deficient | Regulatory judgment |
| Accepting a pharmacopoeial monograph | Licence and identity verification |
| Changing `effective_from` or `effective_to` | Legal applicability |

---

## 6. Audit Trail

- All source registrations are persisted in `local_indexes/registry.json`
- All citation audits are recorded in `validation/v1.1_PAGE_ANCHOR_AUDIT.json`
- All SHA-256 source hashes are recorded in `SHA256SUMS.txt`
- Benchmark runs are recorded in `validation/BENCHMARK_CONSOLE.json`
