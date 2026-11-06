# 18. Complete Corpus and Index Audit
**Generated:** 2026-10-29T09:51:07.498104+00:00
**Version:** v1.4.0

---

## 1. Executive Summary

| Collection | Sources | Chunks | Status |
|---|---|---|---|
| regulatory_technical_unapproved | 15 | 554 | INDEXED (ACTUAL_CHROMADB) |
| sponsor_dossier_unverified | 43 | 2064 | INDEXED (ACTUAL_CHROMADB) |
| Quarantine HTML | 5 | 0 | QUARANTINED — NOT INDEXED |
| Compendial research (SQLite) | 7064 docs | 13524 passages | QUARANTINED — NOT IN CHROMADB |
| Bible (Monograph) folder | 8047 PDFs + 3771 HTMLs | — | READ-ONLY PHARMACY SOURCE |

**Collection isolation:** PASS
**Coverage verdict:** PARTIAL

---

## 2. Regulatory Sources (Class A)

15 of 16 source PDFs are indexed in the regulatory ChromaDB collection.

| Source ID | Chunks | Status |
|---|---|---|
| ICH-Q11-QA | 20 | INDEXED |
| ICH-Q14 | 45 | INDEXED |
| ICH-Q1A-R2 | 23 | INDEXED |
| ICH-Q1B | 11 | INDEXED |
| ICH-Q2-R2 | 35 | INDEXED |
| ICH-Q3A-R2 | 14 | INDEXED |
| ICH-Q3C-R9 | 57 | INDEXED |
| ICH-Q6A | 48 | INDEXED |
| ICH-Q6B | 20 | INDEXED |
| ICH-Q7 | 49 | INDEXED |
| ICH-Q8-R2 | 28 | INDEXED |
| SAHPRA-PEM-02-V9 | 42 | INDEXED |
| ICH-M4Q-R1 | 80 | INDEXED |
| ICH-Q11 | 39 | INDEXED |
| WHO-TRS1010-A10 | 43 | INDEXED |
| IPRP-QWGG-DS-v1.1 | 0 | NOT_INDEXED |

**Not indexed:** IPRP-QWGG-DS-v1.1

> **IPRP-QWGG-DS-v1.1**: IPRP QWGG Guidance for Quality Assessors present on disk in additional_user_supplied/. Not included in the 15-source regulatory corpus (IPRP guidance is supplementary, not a primary ICH/SAHPRA standard). Eligible for inclusion in future build.

---

## 3. Sponsor Dossier Sources (Class D)

42 of 45 dossier PDFs have indexed chunks.

| Substance | Files | Indexed | Zero-chunk |
|---|---|---|---|
| amlodipine | 16 | 13 | 3 |
| hydrochlorothiazide | 15 | 15 | 0 |
| valsartan | 14 | 14 | 0 |

**Zero-chunk files (not indexed):** dossier_amlodipine_Analytical_methods, dossier_amlodipine_edited_validation-analyt-procedure_22102026, dossier_amlodipine_specification

> 2 amlodipine PDFs (Analytical methods.pdf, specification.pdf) yielded 0 extracted chunks due to scanned/image-only content. Files present; extraction failed.

---

## 4. Quarantine HTML (Class C)

5 HTML files from webofpharma.com are quarantined and **never** loaded into any vector collection.
`approved=False`, `provenance_verified=False` in COPY_MANIFEST.json.

---

## 5. Compendial Research Collection (Quarantined Research)

The `artifacts/quarantine/compendial_discovery.sqlite3` (180.1 MB) contains:

| Family | Documents |
|---|---|
| BP_HTML | 3771 |
| MIXED_GENERAL | 449 |
| PH_EUR_EXTRACT | 2844 |

**Total:** 7064 documents, 13524 passages
**Status:** ALL QUARANTINED — `QUARANTINED_UNVERIFIED_EDITION_RIGHTS_AND_APPLICABILITY`
**ChromaDB:** NOT INDEXED — this material is in SQLite only, for research discovery
**Reason:** webofpharma.com HTML exports; edition, licence, and applicability unverified

---

## 6. Bible (Monograph) Folder

**Path:** `Downloads\Pharmacy\Bible (Monograph)` (read-only)
**Contents:** 8047 PDFs + 3771 HTML files
**Status:** Source material for compendial_discovery.sqlite3 extraction
**ChromaDB:** NOT INDEXED
**Note:** Raw pharmacopoeial source files (BP/Ph.Eur. web exports). Read-only pharmacy source. Already extracted into quarantined compendial_discovery.sqlite3. NOT eligible for regulatory collection without authenticated, licensed source verification.

---

## 7. Collection Isolation Verification

| Check | Result |
|---|---|
| Dossier chunks in regulatory collection | 0 (expected 0) |
| Regulatory chunks in dossier collection | 0 (expected 0) |
| Compendial in ChromaDB | False |
| Quarantine HTML in ChromaDB | False |
| **Verdict** | **PASS** |

---

## 8. Outstanding Gaps

| Item | Status | Blocker |
|---|---|---|
| IPRP-QWGG-DS-v1.1 | NOT_INDEXED | Supplementary guidance; not included in 15-source regulatory corpus. File present. Can be added to future build. |
| Amlodipine Analytical methods.pdf | ZERO_CHUNKS | PDF appears scanned/image-only. Needs OCR pipeline. |
| Amlodipine specification.pdf | ZERO_CHUNKS | PDF appears scanned/image-only. Needs OCR pipeline. |
| Compendial collection | QUARANTINED | Awaiting licensed, authenticated pharmacopoeial source. |
| Expert-labelled metrics | PENDING | No expert-labelled evaluation set available. |

---

*This audit was generated automatically. All findings require human review before use in regulatory decision-making.*
