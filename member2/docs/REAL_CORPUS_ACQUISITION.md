# Authoritative regulatory corpus — acquisition and approval runbook

## Status (15 October 2026)
The **discovery catalogue is verified as to official publishing URLs only**. PDF acquisition and page-level indexing have NOT taken place in the delivery environment: downloads and package installation cannot reach the network. The catalogue contains SAHPRA, ICH and WHO entries; no documents are silently approved.

The catalogue is `regulatory_sources/OFFICIAL_SOURCE_CATALOGUE.json`. Each entry records the authority, document title/code, publisher URL, candidate direct PDF link where independently located, version hint, and **NOT_ACQUIRED / source_approved=false** status. A catalogue entry is **not** equivalent to an indexed corpus.

**Source-quality warning:** the SAHPRA Quality and Bioequivalence v9 PDF official result displays `v8` on its first page and `v9` on later pages. Its publication page states version 9 (updated 23 October 2025). The cover/history must be examined and the inconsistency resolved with domain reviewers before manual approval. This code explicitly requires documentation of the resolution if automatically detected.

## On an Internet-connected authorised research computer

```powershell
python -m pip install -e ".[vector,models,dev]"
python -m m2.source_acquisition --catalogue
python -m m2.source_acquisition --download ICH-M4Q-R1
python -m m2.source_acquisition --download ICH-Q11
python -m m2.source_acquisition --download SAHPRA-PEM-02-V9
python -m m2.source_acquisition --download WHO-TRS1010-A10
```

These commands perform HTTPS official-host checks, PDF header, PDF page-count inspection, SHA256 hashing and acquisition metadata generation. They **do not approve or index**. Missing or redirected links must be resolved manually rather than silently using a mirror. Download is subject to rights of use and project approval. Do not ingest copyrighted pharmacopoeial monographs without a licence.

## Manual curation (mandatory before indexing)

For each candidate PDF, M2 and M5 must verify exact document/edition, source URL, effective dates, applicability to the case and source permissions. After review, complete the explicit attestation (example, edit fields for the genuine evidence):

```powershell
python scripts/curate_verified_source.py `
  --acquisition regulatory_sources/ICH-Q11.acquisition.json `
  --pdf-dir regulatory_sources `
  --registry local_indexes/sources.json `
  --reviewer "Verified staff ID" `
  --verified-version "Q11 verified edition" `
  --licence-assessment "Access and indexing permissions checked by the institution" `
  --applicability-assessment "Applicable regulatory context and submission class checked" `
  --effective-from 2012-01-01
```

**Do not copy the example effective date**; use the verified effective/adoption date or omit it and let effective-date-filtered queries fail closed. If the SAHPRA cover discrepancy is detected, provide `--cover-discrepancy-resolution` with a specific documented rationale.

The script verifies the acquired file hash and records the review attestation; it cannot independently verify reviewer identity or legal authorisation. M5/institutional governance must confirm those separately.

## Actual source indexing

Copy `config/production.template.json` to `config/local.json`, then set `registry_path` to the curated manifest, `backend` to `chroma`, `embedding_model` to the agreed downloaded BGE model and `mode` to `research`. Run:

```powershell
python -m m2.cli --config config/local.json ingest-pdf --source ICH-Q11 --pdf regulatory_sources/ICH-Q11.pdf
python -m m2.cli --config config/local.json search "drug substance development manufacturing control strategy"
python -m m2.chroma_validation --out validation/CHROMA_RUNTIME_CHECK.json
```

Verify resulting retrieved passages against the PDF page and section *by hand*, including page offsets, exact original wording, applicability and citation link. For scanned PDFs, hand off to M3's OCR instead of indexing empty pages. Preserve downloaded source binaries locally under the approved access controls and do not commit licensed documents or confidential sponsor dossiers to Git.
