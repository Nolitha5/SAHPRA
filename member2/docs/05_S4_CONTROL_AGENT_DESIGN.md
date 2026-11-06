# S.4 Control Agent Design
**Version:** 1.2 | **Date:** 2026-10-28

---

## 1. Purpose

The S.4 Control Agent produces provisional, cited, human-review-required findings for
CTD Module 3.2.S.4 (Control of Drug Substance) subsections 4.1–4.5.
It does not issue compliance verdicts or approve/reject submissions.

---

## 2. Subsection Coverage

| Subsection | Topic | Key Extraction Terms |
|------------|-------|----------------------|
| 3.2.S.4.1 | Specification | specification, acceptance criteria, limits |
| 3.2.S.4.2 | Analytical Procedures | HPLC, GC, UV, LC-MS, analytical method |
| 3.2.S.4.3 | Validation of Analytical Procedures | validation, accuracy, precision, linearity, robustness |
| 3.2.S.4.4 | Batch Analyses | batch, CoA, certificate of analysis |
| 3.2.S.4.5 | Justification of Specification | specification, justification, acceptance criteria |

---

## 3. Finding Structure

Every `Finding` includes:

| Field | Description |
|-------|-------------|
| `finding_id` | SHA-256-based unique identifier |
| `case_id` | Dossier case identifier |
| `agent_id` | Always `"S4_CONTROL"` |
| `ctd_section` | Specific 3.2.S.4.x subsection |
| `issue_type` | Subsection label (e.g., "Specification") |
| `status` | REVIEW_REQUIRED / POTENTIAL_GAP / MISSING_INFORMATION / INSUFFICIENT_EVIDENCE |
| `sponsor_evidence` | Up to 8 sponsor dossier passages per subsection |
| `regulatory_evidence` | Retrieved regulatory passages (with citations) |
| `rationale` | Deterministic explanation text |
| `uncertainty` | 0.65 (evidence found) or 0.90 (missing/insufficient) |
| `qa_status` | PENDING (always; set by M4/human review) |
| `requires_human_review` | True (always) |
| `attributes` | Extraction hints and evidence status metadata |

---

## 4. Numeric Batch Analysis (S.4.4)

`s4_rules.compare_sponsor_batch_data()` extracts numeric comparisons from sponsor dossier chunks:
- Identifies test name, reported value, stated specification limit
- Checks internal consistency (e.g., value exceeds stated limit)
- Flags inconsistencies as POTENTIAL_GAP findings
- **Never invents numerical thresholds** — only uses values from the sponsor submission

---

## 5. Status Logic

```
if no sponsor content tagged for subsection:
    → MISSING_INFORMATION (uncertainty=0.90)
elif no regulatory evidence found:
    → INSUFFICIENT_EVIDENCE (uncertainty=0.90)
else:
    → REVIEW_REQUIRED (uncertainty=0.65)
    optional: LLM gap analysis (if Ollama available)
```

---

## 6. Safety Guarantees

- `requires_human_review = True` on every finding; enforced by schema.
- No automated compliance conclusion is asserted.
- No regulatory threshold is invented; only sponsor-submitted values used in numeric checks.
- LLM narrative is optional and clearly attributed; it does not override deterministic status.
- Findings from unapproved or unverified sources are never returned.

---

## 7. Test Coverage

Key test file: `tests/test_s4.py`
- All 5 subsections produce findings
- Missing sponsor content → MISSING_INFORMATION
- No regulatory evidence → INSUFFICIENT_EVIDENCE
- Numeric comparison flags inconsistent batch results
- All findings have `requires_human_review=True`
- `finding_id` is stable and unique
