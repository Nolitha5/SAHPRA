# Member 2 real regulatory corpus: acquisition and indexing v0.3

## What is verified, and what is not

The user supplied three real regulatory PDFs: ICH M4Q(R1), ICH Q11, and WHO TRS 1010 Annex 10. They are included in `regulatory_sources/user_supplied_unapproved/` and indexed to `artifacts/real_corpus`. The two uploaded Q11 copies had matching SHA-256 bytes, so the release includes only one Q11.

The source manifest records exact SHA-256 hashes, PDF page counts, IDs and original official reference URLs. The text extracted from the user's files contains the expected document titles/versions; this **does not establish a bitwise match against publisher downloads**, nor legal suitability, applicability to a particular dossier, or SAHPRA approval. `regulatory_approved` is intentionally false.

### Source types and responsibilities

- **RKB**: regulator-authored guidance (ICH/SAHPRA/WHO) as an authoritative *reference origin*, not automatically applicable law.
- **Dossier**: sponsor-submitted case materials in M3/M4 controlled storage. Never mix into the normative RKB.
- **Publication date and version**: not equivalent to *regional effective date*; source use for historical submissions must be qualified.
- **Technical preview**: SQLite-persistent hash-vector + BM25 reciprocal-rank fusion index. It is **not** actual Chroma/BGE retrieval nor a validated ranking system.

## Included contents

- 3 PDFs; de-duplicated user uploads.
- `REGULATORY_CHUNKS.jsonl`: PDF-page-anchored chunks retaining passage texts.
- `REAL_CORPUS_MANIFEST.json`: source hashes, PDF page count, chunk count, research status, cautions.
- `real_reference_preview.sqlite3`: persistent engineering preview index; no remote runtime required.
- `SOURCE_REGISTER.csv`: simple source register.
- `QUERY_SMOKE_RESULTS.json`: machine-generated, **not expert-labelled**, factual source lookup smoke tests.

## Search bundled real data

```powershell
python -m m2.real_corpus search --index artifacts/real_corpus --query '3.2.S.4.3 analytical validation information' --code 'M4Q(R1)'
```

## Repeat user-uploaded source indexing

```powershell
python -m m2.real_corpus index `
  --m4q regulatory_sources/user_supplied_unapproved/ICH-M4Q-R1.pdf `
  --q11 regulatory_sources/user_supplied_unapproved/ICH-Q11.pdf `
  --who regulatory_sources/user_supplied_unapproved/WHO-TRS1010-Annex10.pdf `
  --out artifacts/real_corpus
```

The chunker preserves source and PDF page anchors. It flags likely table-of-contents pages; preview search suppresses these to rank substantive passages first. It does not OCR figures/tables; M3 owns document parsing quality and OCR improvements.

## Obtain additional official sources on an internet-connected computer

An official-domain **download queue** is provided in `regulatory_sources/OFFICIAL_ADDITIONAL_DOWNLOAD_QUEUE.json`, including SAHPRA Quality & Bioequivalence v9, ICH Q6A (EMA-hosted), Q2(R2), Q14, Q3A(R2), Q3C(R9), Q1A(R2), Q11 Q&A and optionally Q6B. Links were discovered from official publisher sources; URLs may change. The downloader checks HTTPS allowlist, redirects, PDF magic bytes, page count, per-file maximum size, and writes SHA-256 acquisition sidecars. It **never marks a source approved**.

```powershell
python scripts/acquire_official_additional.py --catalogue regulatory_sources/OFFICIAL_ADDITIONAL_DOWNLOAD_QUEUE.json --dest regulatory_sources/additional_unapproved
```

**Mandatory**: inspect downloaded material, inspect the SAHPRA page-one v8/v9 header discrepancy, establish document edition/effective date and corpus licensing, and gain required source approval before using it in real assessments. For a technical-only expanded preview, re-index with:

```powershell
python -m m2.real_corpus index --m4q regulatory_sources/user_supplied_unapproved/ICH-M4Q-R1.pdf --q11 regulatory_sources/user_supplied_unapproved/ICH-Q11.pdf --who regulatory_sources/user_supplied_unapproved/WHO-TRS1010-Annex10.pdf --additional-dir regulatory_sources/additional_unapproved --out artifacts/real_corpus
```

Downloaded additional sources remain **unapproved** and cannot bypass the production `SourceRegistry` validation. The preview index and manifest explicitly disclose that approval is pending.

## Actual ChromaDB/BGE index on user computer

```powershell
python -m pip install -e '.[vector,models,dev]'
python scripts/build_real_chroma_on_user_pc.py --index artifacts/real_corpus --chroma-dir artifacts/real_chroma --model BAAI/bge-large-en-v1.5
```

This second script first checks the PDFs' SHA-256 hashes against the local preview manifest. **For additional sources**, the script also checks `regulatory_sources/additional_unapproved` and verifies source hashes before indexing; no expert approval is implied. The script writes `ACTUAL_CHROMA_RUN.json` only after a real Chroma read/write/query succeeds. Running the script requires installed ChromaDB and sentence-transformers, and actual model weights; this container does not contain them.

## Important research caution

**Do not treat source indexing as model training/fine-tuning.** Retrieval-augmented generation references external regulatory evidence during inference. Training would be a different research activity requiring suitable data, licensing and validation.

No expert-labelled retrieval accuracy, evidence faithfulness, source applicability, or real controlled SAHPRA pilot is claimed by this v0.3 package.
