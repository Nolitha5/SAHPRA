# Member 2 · WHO Pharmacopoeial Monograph Acquisition and Indexing (v0.8)

**Research scope:** Pharmaceutical *drug substances* in module 3.2.S (not finished-dose forms). All four are WHO International Pharmacopoeia API monographs. WHO's public PDF links and archive naming may change. An accessible WHO PDF is not necessarily a legal standard for a particular South African submission: M5/domain assessors determine reference edition and applicability; the responsible human regulator decides dispositions.

## Outcomes in this release (19 Oct 2026)

- Four public WHO API **landing-page references** verified with varying PDF-link reliability.
- Downloader now checks page redirects, PDF identity, expected CAS, edition text, retains SHA-256, stores sources **pending review**.
- Automated downloader **attempted here and failed** (container DNS disabled): **0 of 4 PDFs acquired**, **0 WHO monographs actually indexed**.
- `chromadb` and `sentence_transformers` are **not installed in this runtime** and cannot currently be installed due network restrictions. Native Chroma/BGE test **not executed**.
- Existing 15 ICH/WHO/SAHPRA regulatory PDFs and 554 offline-preview passages remain unchanged.
- **104 automated tests pass**, including simulated WHO PDF responses. These are software tests, not retrieval quality scores, not expert-reviewed evidence.

## Document identity and source URLs

| Monograph | CAS | Official WHO page | PDF URL status |
|---|---|---|---|
| Paracetamol | 103-90-2 | https://digicollections.net/phint/en/d/Jb/6.1.264.html | WHO candidate PDF link, browser occasionally 404 |
| Ibuprofen | 15687-27-1 | https://digicollections.net/phint/en/d/Jb/6.1.193.html | WHO PDF indexed by publisher; sometimes browser 404 |
| Amoxicillin trihydrate | 61336-70-7 | https://digicollections.net/phint/en/d/Jb/6.1.19.html | WHO direct four-page PDF readable in research browser |
| Metronidazole **(not metronidazole benzoate)** | 443-48-1 | https://digicollections.net/phint/en/d/Jb/6.1.236.html | WHO PDF at `.../6.1.236.Metronidazole-(Metronidazolum).pdf`; check CAS and title |

Edition caveat: Some HTML headings say Twelfth Edition while a fetched PDF for amoxicillin says Thirteenth Edition, 2025. Keep both exact PDFs and the evidence of their respective editions if distinct; do not automatically resolve or overwrite. PDF metadata is extracted, but an applicability decision requires a qualified assessor. Do not apply a 2025 source to a 2024 submission without determining historical applicability.

## A. Automated WHO PDF download (Windows PowerShell)

```powershell
cd SAHPRA_Member2_WHO_Monograph_Acquisition_v0.8
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,vector,models]"
python scripts/acquire_who_monographs.py
python scripts/verify_who_pending_pdfs.py
```

You do **not** need to download manually if the downloader succeeds. If it reports a failing ID, open its publisher HTML page, select **Open section in PDF format** and save the resulting WHO PDF. For a manual file, import it with:

```powershell
python scripts/add_local_who_pdf.py --id WHO-PHINT-PARACETAMOL-API --file "C:\Downloads\paracetamol.pdf"
```

Repeat with IDs `WHO-PHINT-IBUPROFEN-API`, `WHO-PHINT-AMOXICILLIN-TRIHYDRATE-API`, `WHO-PHINT-METRONIDAZOLE-API`. This command checks identity and CAS and preserves the original into `pharmacopoeia/acquired_pending_review` under a canonical filename. It does not assert rights, licence, correct edition or regulatory applicability.

## B. Native ChromaDB + BGE technical sandbox (unreviewed)

Once the four PDFs are in quarantine and ChromaDB/model weights are installed:

```powershell
python scripts/build_phint_research_chroma.py --model BAAI/bge-large-en-v1.5
```

This produces `local_indexes/phint_research_UNAPPROVED/RESEARCH_INDEX_REPORT.json`. It checks source hashes, reopens ChromaDB and performs a retrieval smoke test. **Never configure M1 or M5's assessor endpoints to retrieve from this unapproved namespace**. An index built from documents not yet attested for applicability is an **engineering** index.

## C. Reviewed compendial RKB and M1/M5 service

M5 or an authorised subject-matter reviewer must record (1) verified edition; (2) permission to index; (3) jurisdiction/submission-date applicability; (4) reviewer identity and credentials; (5) exact source citation. Once genuinely attested, run `scripts/phint_manage.py import-reviewed` (usage detailed in `docs/PHARMACOPOEIAL_EXTENSION_v0.7.md`) and then:

```powershell
python scripts/build_phint_chroma.py --model BAAI/bge-large-en-v1.5
```

The isolated approved-RKB builder refuses metadata-only links and hash mismatches. It is never an automatic drug approval tool.

## D. Evaluation handoff to M5 and M4

`examples/PHINT_M5_SUBSTANCE_EVALUATION_DRAFT.json` contains four substance-specific question starters. Fields such as `expert_label`, `expected_page`, `expected_verbatim_excerpt`, and `applicable_edition_verified` are intentionally blank. M5 provides independent source-anchored ground truth; M4 scores section finding quality and missed deficiencies; M2 scores retrieval Precision@K, Recall@K, MRR/nDCG **only after labels and source applicability are validated**. No automatic passing/rejection of pharmaceutical submissions.

## E. When to ask for help

If the downloader cannot reach WHO, the user may download PDFs on their connected machine or upload **the four original WHO monograph PDF files** to this conversation for further processing. If the Chroma/BGE runner fails, provide its terminal output and `RESEARCH_INDEX_REPORT.json` (where produced); do not post private sponsor dossiers.
