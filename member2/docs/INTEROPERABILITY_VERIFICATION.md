# Member 1–5 interoperability and evidence gates

**Architecture rule:** Member 1 owns runtime, `/analyse`, StateGraph and human gate. Specialist agents do not directly orchestrate one another. Member 2 owns one RERA service and S.4 agent; M4 owns memory/audit; M5 owns QA and UI. All share the Finding schema.

## Contract acceptance matrix
| Counterparty | M2 receives | M2 provides | Live acceptance test required |
| --- | --- | --- | --- |
| M1 | Graph contract, Pydantic Finding model, access policies | `evidence_node(runtime)`, `s4_node(runtime)` or `/m2/evidence`, `/m2/s4/review` | Real M1 graph calls both and receives typed results; retry, timeout, auth checked |
| M3 | Section-tagged dossier chunks and table rows; OCR/quality flags | Chunk/schema validation, source indexing | Actual S.4 eCTD document parsing retains page and 3.2.S.4.x sections |
| M4 | Audit & memory API, evaluation harness | Full retrieval outputs, per-query ranks, S.4 findings | Case history persists across genuine orchestration steps and M4 scores retrieval |
| M5 | Approved sources, labelled query-evidence pairs, QA rubric | Source/edition retrieval incl S.5, all S.4 findings | QA/Critic audits citations and human UI displays every flag without suppressing it |

`python -m m2.team_simulation` runs a **synthetic interoperability contract demonstration** with genuine M2 code and simulator stubs for M1, M3, M4 and M5. It is not a test of their actual implementations.

## Contract freeze questions
1. Should M1 call a Python tool or the authenticated FastAPI router? Pick one integration adapter first and verify both only if required.
2. Match `Finding`, `DossierChunk`, `EvidenceRequest/Result` models precisely. M1's model is authoritative once finalized.
3. Set case-level RBAC/ABAC and avoid indexing sponsor dossiers into the regulation RKB.
4. Define a stable error taxonomy: insufficient regulatory evidence, source version unavailable, extraction failure, index/unavailable error, denied access.
5. Decide how to map M5 PASS/FLAG/ESCALATE workflow to evidence quality classifications without conflating human dispositions.
6. Ensure that all retrieval citations are human-verifiable (authority, code, version, source page/section, URL/hash) and that M4 audit records source versions and index identifiers.

## Live integration proof, to collect from members
- M1: graph trace and endpoint test with actual S.1 and S.4, plus M1 `/analyse` response.
- M3: actual structured data extraction from de-identified or synthetic dossier PDFs including tables and CTD section tags.
- M4: durable audit export + A–D evaluation harness run.
- M5: scientific QA records, approved gold labels, UI screenshot, authorised reviewer decisions.

Store these in `integration_evidence/` (folder placeholder). Merely placing a file there does not demonstrate validity; each artifact needs review.
