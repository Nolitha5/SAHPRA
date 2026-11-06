> **Historical v0.4 snapshot.** This report reflects the earlier 3-PDF state. For current status (15 PDFs), use `REAL_REGULATORY_CORPUS_VERIFICATION_v0.5.md`.

# Member 2 Regulatory Knowledge Base — source collection v0.4

**Date checked:** 19 October 2026. **Stage:** Technical acquisition and indexing, *not* human-certified regulatory applicability, production deployment, LLM fine-tuning, or clinical/regulatory validation.

## What the ZIP really contains

**Three genuine user-provided PDF references:** ICH M4Q(R1), ICH Q11, WHO TRS 1010 Annex 10. An identical duplicate ICH Q11 upload was excluded. The package retains their page-level extraction and persistent experimental SQLite retrieval index; SHA-256 digests establish identity of the supplied local files. The three PDFs have **not** been byte-matched against the official publisher copies and none is approved for a specific case.

**Twelve additional official publisher PDF candidates:** primary links verified through online research but **not downloaded in this environment** due network/DNS restrictions. They are listed in `regulatory_sources/OFFICIAL_ADDITIONAL_DOWNLOAD_QUEUE.json` and `regulatory_sources/REGULATORY_DOCUMENT_INVENTORY_v0.4.csv` with per-file inclusion status. Open `docs/OFFICIAL_PDF_DOWNLOAD_LINKS.html` to access each publisher PDF manually.

## Coverage / selection principles

Core S.4 reference candidates: ICH M4Q(R1), Q6A, Q2(R2), Q14, Q3A(R2), Q3C(R9), Q11 and SAHPRA SAHPGL-PEM-02 v9. Cross-section stability sources: WHO TRS 1010 Annex 10, ICH Q1A(R2). Supplementary interpretive and process references: Q11 Q&A, Q1B, Q7, Q8(R2). ICH Q6B is **conditional** on biotech/biologics study scope; do not apply it to unrelated substances. Licence-restricted pharmacopoeial BP/USP/Ph.Eur. monographs remain **unavailable and excluded**. Document coverage is not proof of exhaustive regulation. Confirm scope/applicability with the M5 domain lead and supervising assessor.

**M4Q(R2) warning:** An ICH draft Step 2b was published for public consultation in 2025 and the ICH work plan forecasts Step 4 final adoption in 2027. Retain final M4Q(R1) as this project's initial CTD structure basis; do not silently replace it with an M4Q(R2) draft. Verify status at each subsequent corpus refresh.

**SAHPRA version issue:** Official catalogue reports SAHPGL-PEM-02 **v9**, updated **23 October 2025**. A previous online inspection noted conflicting v8/v9 indications on the source's cover/headers. Flag for reviewer confirmation, not auto-acceptance.

**ICH Q2(R2):** The official PDF's history lists 1 November 2023 Step 4 adoption and subsequent corrections, including a 4 April 2025 formatting/reference update. Keep that version distinction when testing historical submissions.

## Windows PowerShell — one-command pipeline

From the extracted project root (requires Python 3.11 or 3.12 and Internet access):

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python scripts/collect_validate_index.py                  # inspect coverage only
python scripts/collect_validate_index.py --download       # download available official PDFs, pending review
python scripts/collect_validate_index.py --index          # rebuild local TECHNICAL preview using present documents
python -m m2.real_corpus search --index artifacts/real_corpus --query "validation of analytical procedures" --code "Q2(R2)"
python -m pytest -q
```

To include biotech-specific Q6B, **only after confirming scope**:

```powershell
python scripts/collect_validate_index.py --download --include-conditional
python scripts/collect_validate_index.py --index --include-conditional
```

To fetch one specific document only:

```powershell
python scripts/collect_validate_index.py --download --id ICH-Q6A
```

Downloaded PDFs enter `regulatory_sources/additional_unapproved/`. The script never overwrites an existing file and writes a local SHA-256, page count and acquisition sidecar. A checksum proves file consistency, **not regulatory validity**. If an official URL redirects to an unrecognised host, acquisition intentionally fails; review and update the strict allowlist, don't disable safety checks.

## Build *actual* ChromaDB / BGE retrieval

```powershell
python -m pip install -e ".[vector,models,dev]"
python scripts/collect_validate_index.py --index
python scripts/build_real_chroma_on_user_pc.py --index artifacts/real_corpus --chroma-dir artifacts/real_chroma --model BAAI/bge-large-en-v1.5
```

The actual build checks document hashes against the manifest, creates a persistent ChromaDB collection and queries it using a real sentence-transformers embedding model. A successful result writes `artifacts/real_chroma/ACTUAL_CHROMA_RUN.json`. This **has not run or passed** in the current container. Never claim that the SQLite/hash baseline represents real BGE/Chroma metrics.

## Team review and evaluation gates

- **M3:** verify OCR/tables, section tagging and extraction quality for the acquired PDFs.
- **M5 / regulatory supervisor:** approve source versions, inclusion/exclusion criteria, the permissible use of pharmacopoeial materials, applicable jurisdiction and submission date; prepare expert-labelled question→passage pairs.
- **M2:** check no broken anchors or duplicate pages, record SHA-256 + version, index the approved technical corpus, run and report reproducible retrieval experiments.
- **M4:** evaluate gold queries using retrieval metrics plus the group harness, but only after adjudicated expert labels are signed off.
- **M1:** connect RERA/S.4 interfaces to orchestration; QA and human assessor must validate final findings.

## Source links and licensing

Official links are in the JSON/CSV inventory and local HTML index; they are for researcher-authorised retrieval only. Copyright and local redistribution/fine-tuning permissions differ across publishers and individual monographs. Neither internet access nor the presence of a download link constitutes permission to use a publication for arbitrary model training, nor proof that the guideline applies to the specific application under review.
