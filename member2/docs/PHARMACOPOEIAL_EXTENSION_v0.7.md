# Pharmacopoeial Knowledge Extension — Member 2, v0.7

**Status as at 19 October 2026:** Functional reference catalogue, substance identity resolution, guarded local PDF import, M1/M5 compatible evidence endpoint and isolated ChromaDB/BGE index builder implemented. **No WHO monograph PDFs or proprietary pharmacopoeial texts are physically included or claimed indexed in this version.** The existing 15 ICH/WHO/SAHPRA regulatory reference PDFs remain unchanged, with 554 passages in the separate offline technical preview. The earlier engineering benchmark and all previous scripts remain present.

## 1. Research intent and decision authority

The feasibility study is a human-in-the-loop evaluation of Module **3.2.S, Drug Substance**, not an autonomous marketing-authorization tool. RERA retrieves evidence; S.4 Control proposes documentation/technical findings; S.5 (Member 5) examines reference-standard and monograph claims; M5 QA reviews evidence; and a human SAHPRA assessor decides the regulatory disposition. No route or model makes drug approval decisions.

## 2. Source architecture

- **Layer A: Regulatory guidelines** — the 15 user-supplied ICH, WHO and SAHPRA PDFs retained from v0.6. Existing `artifacts/real_corpus/` is an engineering-preview SQLite index, **not BGE/Chroma**.
- **Layer B: Pharmacopoeial references** — `pharmacopoeia/WHO_PHINT_RESEARCH_CATALOGUE_v0.7.json` catalogs four WHO active-substance monographs and three WHO General Notices by verified publisher URL. This metadata-only discovery catalogue does **not** claim their full contents are downloaded, licensable or indexed.
- **Layer C: Approved compendial local PDFs** — intentionally empty until PDF acquisition and human-attested licence, edition, provenance and applicability review. `scripts/phint_manage.py import-reviewed` produces page-linked chunks and a **separate** Ph.Int. source registry. Synthetic test-only PDFs are made dynamically during tests, not bundled as standards.
- **Layer D: Isolated Ph.Int. vector store** — `scripts/build_phint_chroma.py` uses the separately reviewed PDF chunks and real BGE embeddings on a dependency-enabled workstation. It never merges unreviewed monographs into guidelines or case-data stores.
- **Sponsor dossiers and assessor decisions** — not stored in the compendial RKB; M3 owns dossier extraction, M4 case memory and audit, M1 shared workflow integration.

## 3. Research shortlist and why

| Item | Direct online reference | RKB purpose |
|---|---|---|
| Paracetamol API | https://digicollections.net/phint/en/d/Jb/6.1.264.html | Matching an API by name/alias/CAS to an exact monograph |
| Ibuprofen API | https://digicollections.net/phint/en/d/Jb/6.1.193.html | Distinguishing substance-specific assay, identity and impurity reference material |
| Amoxicillin trihydrate API | https://digicollections.net/phint/en/d/Jb/6.1.19.html | Test case with especially important edition-label discrepancy |
| Metronidazole API | https://digicollections.net/phint/en/d/Jb/6.1.236.html | Another API-specific monograph retrieval pathway |
| General Notices — Definition | https://digicollections.net/phint/en/d/Jb/4.5.html | Interpretation of how monographs apply |
| General Notices — Storage | https://digicollections.net/phint/en/d/Jb/4.10.html | Container/storage terminology; supports M4 stability and closure checks |
| General Notices — Manufacture | https://digicollections.net/phint/en/d/Jb/4.6.html | Manufacturing context for M3 |

**Web-verification caveat:** The WHO digital collection presented a *Twelfth Edition* title on some monograph HTML pages while an opened Amoxicillin trihydrate PDF presented *Thirteenth Edition, 2025* page text. The catalogue explicitly stores `ONLINE_2025_REQUIRES_VERIFICATION` and a discrepancy flag. A 2025 page timestamp cannot substitute for confirmed legal effective dates or applicability to a South African application. Some online PDF link targets returned 404 during verification, so only the Amoxicillin direct PDF URL is configured for automated download; the others must be obtained from their original publisher page and added manually. Links may change over time.

## 4. Reproducible workflows on Windows

Extract project ZIP, navigate into its root, then:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"

# These three commands require NO pharmacopoeial PDF download.
python scripts/phint_manage.py list
python scripts/phint_manage.py status
python scripts/phint_manage.py resolve --substance "Acetaminophen" --cas "103-90-2"

# This demonstrates deliberate NON-approval and no fabricated evidence.
python scripts/demo_phint_reference_lookup.py

# If publisher access is available, a real PDF link was verified for the
# Amoxicillin trihydrate reference, subject to publisher access availability.
python scripts/phint_manage.py download --id WHO-PHINT-AMOXICILLIN-TRIHYDRATE-API
```

For any other monograph, use its official `online_url`, obtain an authorised *PDF* directly where possible, retain its original source URL, and supply that PDF to the guarded import command below. Do not scrape a restricted subscription, bypass credentials or assume online reading permits machine indexing.

```powershell
# This is a template. Replace ALL illustrative attestation text with genuine
# domain/rights decisions; DO NOT run this unchanged as a claim of expert review.
python scripts/phint_manage.py import-reviewed `
  --id WHO-PHINT-PARACETAMOL-API `
  --pdf "C:\path\to\authorised\paracetamol-monograph.pdf" `
  --edition "ACTUAL VERIFIED COMPENDIUM EDITION" `
  --reviewer "REAL REVIEWER NAME AND POSITION" `
  --rights-note "DOCUMENTED LICENCE/REUSE AUTHORISATION FOR LOCAL INDEXING" `
  --applicability-note "DOCUMENTED SAHPRA/CASE APPLICABILITY REASONING" `
  --edition-note "Edition discrepancy resolved in regulator-reviewed source inspection" `
  --effective-from 2025-01-01
```

The `--effective-from` date above is illustrative. Use only a confirmed, applicable effective date; leave it blank when unknown, in which case effective-date-filtered retrieval fails closed.

### Build the **real** pharmacopoeial vector index only after review

```powershell
python -m pip install -e ".[vector,models,dev]"
python scripts/build_phint_chroma.py --model BAAI/bge-large-en-v1.5
```

The command requires locally reviewed PDF content; it will **fail rather than build from metadata-only links**. Model weights are downloaded separately when the workstation permits. A successful index is technical, not SAHPRA endorsement or a drug approval.

## 5. Integration with all members

**M1 Orchestrator** can call the protected `POST /m2/phint/evidence` route; in research mode it must supply `M2_SERVICE_TOKEN`, and the runtime needs `M2_PHINT_CATALOGUE` set to this package's WHO catalogue path. Returned fields include `lookup_status`, `candidates`, `evidence`, `human_review_required`, and `regulatory_approval_or_rejection: null`.

**M2 S.4 Control** receives a Section 3.2.S.4 dossier extract from M3, finds a plausible API monograph through the catalogue, requests applicable citation-bearing requirements from RERA after reviewed import, and compares dossier observations without automatic approval or rejection.

**M3 Perception** retains original dossier/source identity, extraction quality, page locations and structured analytical tables. M2 does not replace its OCR and table-processing pipeline.

**M4 Cross-Section/Evaluation** can trace S.4 specification and monograph references to S.2/3/6/7, while keeping operational memory separate from the compendial RKB. Its evaluation harness receives query/evidence labels **only after expert review**.

**M5 S.5/QA** provides compendial applicability, historical edition confirmation, domain gold labels, and checking of citation support and human-gate outputs. It should not treat a reference-only discovery result as authoritative evidence.

## 6. Acceptance and outstanding work

| Requirement | Outcome |
|---|---|
| Research catalogue and online reference links | Implemented for seven WHO Ph.Int. entries |
| Name, synonym, CAS matching and CTD scope checks | Implemented/tested |
| Conflicting identifiers and no-match | Implemented/tested, human review |
| Licence, applicability, edition, PDF identity and hash gating | Implemented/tested using **synthetic-only PDF fixtures** |
| Retained reviewer-attested original and exact PDF pages | Implemented/tested using synthetic PDFs |
| M1/M5 interface without automatic verdicts | Implemented/tested |
| Actual WHO monograph PDF acquisition in this runtime | BLOCKED by container DNS/network access |
| Real WHO monograph chunks in ChromaDB/BGE | NOT PERFORMED: PDFs, dependencies, reviews missing |
| Source-specific expert evaluation | NOT PERFORMED: M5/assessor gold labels not provided |
| Regulatory acceptance / pilot approval | OUT OF SCOPE for this development package |

**Critical distinction:** WHO describes the International Pharmacopoeia as a reference for specifications and tests, but its existence or online availability does **not** automatically make each monograph legally applicable to a particular SAHPRA submission. Apply the reviewed effective edition and jurisdictional requirements rather than choosing the latest searchable webpage.
