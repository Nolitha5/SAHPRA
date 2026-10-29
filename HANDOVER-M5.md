# M5 Handover Summary — Phase 0–6

**Date:** 2026-10-28  
**Component:** Member 5 — QA, Interface & Domain  
**Study:** SAHPRA Agentic QA-RAG Feasibility (Module 3.2.S Drug Substance)

---

## What was done

### Phase 0 — Inspection (read-only)
Mapped every file in the project. Identified two independent backends (Express scaffold port 3000, FastAPI M5 port 8000), confirmed the frontend calls only FastAPI, located all tests and golden fixtures, and documented known gaps before any code was changed.

### Phase 1 — Backend clarity
- Added an orientation note to `README.md` directing readers to `README-M5.md` for the M5 FastAPI backend. No Express files were deleted.
- Confirmed: frontend has zero dependency on Express. All M5 UI calls go to `http://localhost:8000`.

### Phase 2 — QA/Critic strengthening
- Removed the dead `ReviewRequest` class from `backend/main.py` (line 69, never referenced anywhere).
- Added `test_mock_findings_f005_out_of_range_score_is_flagged`: loads `mock_findings.json` directly, asserts F-005 (score 150) lands FLAG or ESCALATE — not PASS.

### Phase 3 — S.5 agent strengthening
- Added `test_golden_outdated_standard_s5_verdict` to `test_s5_standards.py`.
- This test exercises the previously untested S.5 layer of `scenario_outdated_standard.json`: loads `input.s5_claim`, calls `check_s5_claim`, asserts verdict=NON_COMPLIANT and edition_current="BP 2024".

### Phase 4 — Assessor UI
Three issues addressed in the React frontend:

| Issue | Fix |
|---|---|
| `alert()` on submit failure — blocking, inaccessible | Replaced with inline `<p class="submit-error" role="alert">` per finding |
| Optimistic update not rolled back on failure | `App.tsx` snapshots previous state; rolls back on server error |
| `submitted` flag stays `true` after rollback — assessor cannot retry | `useEffect` in `FindingCard` resets `submitted` when finding has no decision and an error is present |

TypeScript compiles clean after these changes (`npx tsc --noEmit` — no errors).

### Phase 5 — Golden scenarios and mock data
- `backend/mock_findings.json` restructured from a plain array to `{_meta, findings}`. The `_meta` block documents each finding's purpose, explicitly labels F-005 score=150 as intentional, and warns against using this file for all-PASS assertions.
- `backend/adapters/m1_adapter.py` and `test_qa_critic.py` updated to read `data["findings"]`.
- All three golden files (`scenario_pass.json`, `scenario_identity_fail.json`, `scenario_outdated_standard.json`) given `test_coverage` notes in `_meta`. `scenario_outdated_standard.json` bumped to v1.1; `scenario_pass.json` bumped to v1.1 with a note clarifying the F-005 score difference from the mock fixture.

### Phase 6 — Documentation and regression
- `README-M5.md` updated: test count 39 → 41, mock data table updated, golden-schema block updated.
- Full regression run: **41 Python tests pass, 0 TypeScript errors, 4 Node tests pass**.

---

## Test inventory

```
backend/tests/test_qa_critic.py          16 tests
backend/tests/test_s5_standards.py       18 tests
backend/tests/test_golden_scenarios.py    7 tests
                                    ─────────────
                                         41 total
tests/app.test.js (Express scaffold)      4 tests
```

---

## Known limitations (not in scope for this phase set)

| Item | Notes |
|---|---|
| No frontend test runner | Vite/React — no Vitest or Jest configured. UI changes verified by TypeScript only. |
| Express scaffold still present | `src/`, `tests/app.test.js` — confirmed unused by M5; retained as original repo scaffold. Removal requires explicit team approval. |
| M1/M4 adapters are stubs | Both protocols defined; real implementations require endpoint contracts from M1 and M4 teams (documented in `README-M5.md`). |
| `mock_findings.json` read by `GET /findings` endpoint | The FastAPI endpoint serves this file directly; it now returns an object `{_meta, findings}` rather than a bare array. Any external consumer of `GET /findings` that expected an array will need updating. (The UI calls `GET /findings/reviewed` which is unaffected.) |

---

## Files changed in this phase set

| File | Change |
|---|---|
| `README.md` | Orientation note added at top |
| `backend/main.py` | Dead `ReviewRequest` class removed |
| `backend/mock_findings.json` | Restructured to `{_meta, findings}`; F-005 documented |
| `backend/adapters/m1_adapter.py` | Reads `data["findings"]` not bare array |
| `backend/tests/test_qa_critic.py` | Added `test_mock_findings_f005_out_of_range_score_is_flagged` |
| `backend/tests/test_s5_standards.py` | Added `test_golden_outdated_standard_s5_verdict` |
| `tests/golden/scenario_pass.json` | `_meta` bumped to v1.1, `test_coverage` and `findings_note` added |
| `tests/golden/scenario_identity_fail.json` | `_meta` `test_coverage` note added |
| `tests/golden/scenario_outdated_standard.json` | `_meta` bumped to v1.1, `test_coverage` note added |
| `frontend/src/App.tsx` | `submitErrors` state; rollback on failure; passes errors to `SectionGroup` |
| `frontend/src/components/SectionGroup.tsx` | Accepts and threads `submitErrors` |
| `frontend/src/components/FindingCard.tsx` | Accepts `submitError`; inline error banner; `useEffect` retry reset |
| `frontend/src/index.css` | `.submit-error` style added |
| `README-M5.md` | Test count, mock data table, golden-schema block updated |
| `HANDOVER-M5.md` | This file |

---

## Regulatory reminders (unchanged)

- **PASS from QA/Critic = structurally valid, ready for assessor review. It does not mean the substance is compliant.**
- All AI findings are assistance for a human assessor. No finding constitutes autonomous approval or rejection of a medicine.
- All pharmacopoeial edition claims, citations and test results in this codebase are synthetic.
- No real dossier data is present anywhere in this repository.
