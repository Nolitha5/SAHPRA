# Member 3: Dossier ingestion and review

Member 3 prepares evidence from eCTD Module 3.2.S PDFs and generates S.2 Manufacture and S.3 Characterisation findings for assessor review. The package runs locally. Member 1 calls ingestion, Member 2 consumes the chunk payload, and Members 4 and 5 use the structured findings for traceability and QA.

## Install and run

From the repository root in PowerShell, with Python 3.10 or newer:

```powershell
python -m venv member3/.venv
member3/.venv/Scripts/python.exe -m pip install -e member3
member3/.venv/Scripts/python.exe -m unittest discover -s member3/tests -v
member3/.venv/Scripts/m3-ingest.exe member3/examples/sample_dossier.pdf --case-id DEMO --out case_output.json
member3/.venv/Scripts/m3-review.exe member3/examples/sample_dossier.pdf --case-id DEMO --out findings.json
```

On Linux or macOS, use the executables in `member3/.venv/bin` instead. The installed package also supports `python -m m3.cli` and `python -m m3.run_agents`.

Pass multiple PDF paths to either command for one dossier. Identical files are processed once. Section tracking starts independently for each PDF. For a single document, `m3-ingest --document-id ID` can assign a caller-supplied source ID. Use an opaque ID if source filenames are sensitive. Keep input PDFs and generated JSON in the approved dossier storage location.

OCR uses the separately installed Tesseract executable, which must be on `PATH`. Install the required language data and set `--ocr-language` to the corresponding Tesseract code, such as `eng`. A missing engine, timed-out OCR or unreadable page is recorded in the output with its physical page number.

Both commands return `0` when at least one chunk is reviewable, `1` for an input or output error, and `2` when the output was written but all content was excluded from review. An exit code of `0` can include partial extraction warnings. The JSON is written atomically. Inspect the quality flags or extraction findings before passing the output downstream.

## Integration contract

- `ingest_dossier(path, document_id=...)` ingests a single document. `ingest_dossier_files(paths)` ingests a list of PDFs and deduplicates exact files by SHA-256.
- The existing case JSON shape is unchanged: `case_id`, `dossier_chunks`, `as_of`, and `relevant_regulatory_codes`. Each chunk retains `chunk_id`, `document_id`, `ctd_section`, `text`, `page`, `kind`, `table_rows`, `metadata`, and `quality_flag`.
- Page numbers are 1-based physical PDF pages. Text chunks stay on one page and within one section. Chunk size and overlap default to 512 and 128 whitespace-separated words. Chunk IDs incorporate the source file hash, document ID, page, section and position.
- A native table has `kind=table`. `table_rows` contains ordered rows, including the header row when present, using positional keys such as `column_1`. Missing cells are `null`. Native captions have `kind=figure_caption`. OCR fallback produces text.
- `metadata` includes the source SHA-256, extraction source, section confidence, redaction types from the source block, and best-effort document language and confidence. Short or ambiguous inputs may have no detected language.
- `quality_flag` marks evidence excluded from automated review. `UNKNOWN` means that no CTD section could be assigned. An unreadable page resets CTD attribution until a subsequent heading anchors it again. The review CLI carries non-TOC extraction flags into the findings JSON as `M3_INGESTION` quality findings.
- `m3.s2_manufacture.review(case_id, chunks)` and `m3.s3_characterisation.review(case_id, chunks)` preserve the shared finding shape. Findings remain `QAStatus.PENDING` and require human review. Cross-section targets are hints for M4. Regulatory evidence is supplied through M2 when integrated.

## Qualification before live dossiers

The included test and example PDFs contain synthetic data. Native PDF table extraction, page attribution, and basic OCR should be qualified on representative dossier layouts before relying on the results. The current extractor handles detectable native tables and recognisable captions. Borderless or scanned tables, multi-column layouts, and standalone section PDFs without a recognised heading require manual checks or a more capable layout extraction path.

The redactor processes text before chunking or export, and handles common email, phone, South African ID and labelled personal fields. It cannot reliably detect every name, identifier, or confidential field. Validate against an approved confidentiality test set before storing real evidence or sending it to a model. The rule-based S.2/S.3 checks provide review cues. Validate them against the assessor rubric and run a full M1/M2/M5 handoff before live use. S.5 claim extraction remains outside this release.
