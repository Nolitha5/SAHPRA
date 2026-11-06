# Project Scope and Expectations
**Version:** 1.2 | **Date:** 2026-10-28

---

## 1. Research Project

This is a **feasibility research project** investigating whether an Agentic QA-RAG system can support pharmaceutical regulatory quality assessment of CTD Module 3.2.S (Drug Substance).

**It is not a production regulatory system.** No regulatory authority has approved or endorsed it for use in actual medicine assessments.

---

## 2. Member 2 Scope

Member 2 is responsible for:

1. **Evidence/RERA Agent** — retrieves regulatory evidence from an approved source registry.
2. **Regulatory Knowledge Base** — manages and indexes regulatory source documents.
3. **S.4 Control Agent** — produces provisional structured findings for CTD 3.2.S.4.1–3.2.S.4.5.

Member 2 does NOT cover:
- S.1 Identity (Member 1)
- S.2 Manufacture (Member 3)
- S.3 Characterisation (Member 3)
- S.5 Reference Standards (Member 5)
- S.6 Container Closure (Member 4)
- S.7 Stability (Member 4)
- Orchestration and runtime (Member 1)
- Memory and consistency (Member 4)
- Expert evaluation interface (Member 5)

---

## 3. What the System Does

- Retrieves regulatory evidence passages with full provenance citations
- Produces structured provisional findings for S.4 sections
- Flags missing, insufficient or potentially non-compliant dossier content
- Requires human review for every finding

---

## 4. What the System Does NOT Do

- Does not approve, reject or authorise pharmaceutical medicines
- Does not issue compliance certificates
- Does not replace qualified regulatory assessors
- Does not provide legal or clinical advice
- Does not invent regulatory requirements

---

## 5. Assessment Status

Every output from Member 2:
- Is marked `requires_human_review=True`
- Has `qa_status=PENDING`
- Contains explicit `uncertainty` values
- Includes full citation trails for all regulatory evidence

**No output from this system constitutes a regulatory decision.**
