# Member 3 — Ingestion & Perception

Agentic QA-RAG · SAHPRA Module 3.2.S · Branch: `Nduvho-M3`

Turns a raw eCTD Module 3.2.S dossier (PDFs) into clean, CTD-section-tagged,
PII-redacted, retrieval-sized chunks that every other agent in the system
reads — without ever mistaking a limit in `3.2.S.4.1` for one in `3.2.S.7`.

This is the **Tier 0 walking skeleton** for M3, per the team delegation doc:
one dossier in, correctly section-tagged chunks out, in the exact shape M2
already built their S.4 review against. Table extraction (Docling), OCR
tuning, the S.2/S.3 specialist agents, and Presidio-grade PII filtering are
the next layer on top of this proven thread — not required for it to work.

---

## What is built

| Component | Location | Purpose |
|---|---|---|
| **Shared schemas** | `src/m3/schemas.py` | `DossierChunk` (locked 1:1 with M2's `member2/src/m2/schemas.py::DossierChunk` on `aziz-and-sipho`) and `S5Claim` (matches Florah's `backend/models.py::S5Claim` on `Florah-M5`) |
| **CTD section recognition** | `src/m3/ctd_mapping.py` | Regex + state-machine heading detector for `3.2.S.x[.y[.z]]`; the hard, highest-leverage part per the M3 spec |
| **Text & OCR extraction** | `src/m3/extraction.py` | PyMuPDF for born-digital pages; pytesseract OCR fallback for scanned pages (auto-detected per page) |
| **Section-aware chunker** | `src/m3/chunking.py` | 512-token / 128-overlap chunks (per spec default), never crosses a CTD section boundary |
| **PII / confidentiality filter** | `src/m3/pii_filter.py` | Regex first pass (email, SA ID, phone); swap-in point for Presidio once approved |
| **Pipeline orchestration** | `src/m3/pipeline.py` | `ingest_dossier()` — ties extraction → section tagging → chunking → PII redaction → quality flagging into one call |
| **M2-shaped export** | `src/m3/export.py` | Writes the case JSON in the exact shape of M2's `S4ReviewRequest` / `examples/synthetic_s4_case.json` |
| **S.2 Manufacture agent** | `src/m3/s2_manufacture.py` | Completeness/consistency review of 3.2.S.2 (subsections S.2.1–S.2.6 present, manufacturer address, flow-diagram cue, starting-material forward-links); emits `Finding` objects |
| **S.3 Characterisation agent** | `src/m3/s3_characterisation.py` | Structure-elucidation technique check (IR/UV/NMR/MS/elemental) + impurity extraction with cross-section links to S.4/S.2/S.7 |
| **Shared Finding schema** | `src/m3/schemas.py` | `Finding`/`SponsorEvidence`/`FindingStatus`/`QAStatus`, mirroring M2's `member2/src/m2/schemas.py::Finding` exactly |
| **Agent runner** | `src/m3/run_agents.py` | `python -m m3.run_agents dossier.pdf` — ingest + run both agents, emit findings JSON |
| **CLI** | `src/m3/cli.py` | `python -m m3.cli dossier.pdf --case-id ... --out ...` |
| **Tests** | `tests/` | 39 tests, stdlib `unittest`, no pytest dependency — covers section mapping, chunk boundaries, PII redaction, schema contract, and one full synthetic-dossier end-to-end run |

---

## Prerequisites

- Python 3.10+
- `pip install -r requirements.txt`

## Running

```bash
cd member3
python -m unittest discover -s tests -v     # 39 tests, should all pass
python -m m3.cli path/to/dossier.pdf --case-id CASE-001 --out examples/out.json
python -m m3.run_agents path/to/dossier.pdf --case-id CASE-001 --out examples/findings.json
```

A worked example is already committed at `examples/tier0_case_output.json`,
produced from a small synthetic multi-section PDF (`examples/sample_dossier.pdf`,
fictional content only — no real dossier data anywhere in this repo).

---

## The contract (why this shape, not another)

### M3 → M2 (`DossierChunk`)

```python
class DossierChunk:
    chunk_id: str
    document_id: str
    ctd_section: str          # e.g. "3.2.S.4.1"
    text: str
    page: int | None
    kind: str                 # "text" | "table" | "figure_caption"
    table_rows: list[dict]
    metadata: dict
    quality_flag: str | None  # set => M2 excludes it from review
```

Locked against `member2/src/m2/schemas.py::DossierChunk` and
`member2/docs/06_M1_M3_M4_M5_INTEGRATION_CONTRACTS.md` (v1.2) on the
`aziz-and-sipho` branch. **Do not change field names/types without
re-syncing with M2** — this is the seam the whole system depends on.
M2 enforces: only chunks with `ctd_section.startswith("3.2.S.4")` and no
`quality_flag` are reviewed by S.4 Control — so a quality problem must be
flagged, not dropped, or the gap disappears invisibly.

### M3 → M5 (`S5Claim`)

Matches `Florah-M5`'s `backend/models.py::S5Claim` — the structured S.5
sponsor claim (substance, standard, edition claimed, submission date) that
M5's Reference Standards agent checks against current pharmacopoeial
editions. Not yet wired into the pipeline output (S.5 extraction logic is
next); the schema is in place so M5 isn't blocked on the shape.

---

## Golden rule for this layer

Preserve the CTD section on everything, and never let a garbled or empty
extraction pass silently — flag it. Garbage in here becomes a wrong
regulatory finding later. Concretely: any chunk under
`_MIN_CHUNK_CHARS` or that fails the garbled-text heuristic gets
`quality_flag = "GARBLED_OR_EMPTY_EXTRACTION"` rather than being silently
dropped or silently kept.

---

## What's NOT done yet (Tier 0 scope, honestly)

| Gap | Plan |
|---|---|
| Table/figure extraction (spec & stability tables as structured rows) | Docling integration — `table_rows` field exists in the schema, currently always empty |
| Docling / Unstructured / Marker as primary extractor | Currently PyMuPDF only; Docling is the stated workhorse per the spec, swap-in point is `extraction.py` |
| Presidio-grade PII detection | Current filter is regex-only (email/phone/SA ID); Presidio is the documented upgrade path |
| De-duplication across documents | Not implemented — current pipeline is single-PDF |
| Language detection | Not implemented |
| S.5 claim extraction from dossier text | Schema exists (`S5Claim`); no extraction logic yet |

---

## Regulatory note

All output here is extracted structure and text, never a judgement. No
chunk, finding, or flag produced by this pipeline constitutes an approval,
rejection, or regulatory conclusion — that stays with the human SAHPRA
assessor, per the project's one governing rule.
