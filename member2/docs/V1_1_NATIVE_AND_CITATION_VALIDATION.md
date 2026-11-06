# Member 2 v1.1 — token-aligned Chroma/BGE readiness and original-PDF citation audit

**Release purpose:** Incrementally strengthen the existing Member 2 research software while domain-reviewed pharmacopoeial monographs, team implementations and human evaluation are deferred. This is a **technical research package**, not a regulatory decision engine.

## Verified in this container

- The same 15 ICH/WHO/SAHPRA PDFs are preserved under the unapproved source directories. Original SHA-256 checks are enforced against `artifacts/real_corpus/REAL_CORPUS_MANIFEST.json`.
- `python scripts/audit_regulatory_page_citations.py --root .` checks every original PDF for source byte integrity, number of pages, and whether the **whitespace-normalized full retrieved passage** exists on the exact claimed source/PDF page. No inference from the title alone. Output: `validation/v1.1_PAGE_ANCHOR_AUDIT.json`.
- The full-corpus 554 original passages matched their original PDF page anchors (15/15 PDF hashes, 554/554 passage anchors); **this does not measure regulatory applicability, retrieval relevance, page-layout/table interpretation, or expert agreement**.
- Native dependency probe: `validation/v1.1_NATIVE_PREFLIGHT.json` is `BLOCKED` because **ChromaDB and Sentence Transformers are not installed and the container cannot resolve the package index**. No genuine BGE weights or ChromaDB vector index exists in this package; the SQLite/hash/TF-IDF research indexes are not substitutes.
- The quarantine compendial discovery index remains physically and logically separate from authoritative regulatory retrieval. No unreviewed monographs, BP/Ph. Eur. mirrors, or online references have been promoted to approved regulatory evidence.

## New safe token-aligned chunks

`src/m2/token_safe_index.py` implements model-specific exact-source-substring splitting with a **fast Hugging Face tokenizer that provides character offsets**. Each derived chunk retains its source ID, original PDF page, section, parent chunk ID, original character offsets, text SHA-256, tokenizer identifier and token range. It refuses non-fast/offset-less tokenizers or unsafe token budgets.

`run_native_bge_chroma_validation.py` now selects the token-aware pipeline by default. It verifies all original PDFs against SHA-256, validates the original index, loads BGE, audits original token lengths, rechunks with the actual model tokenizer, verifies the output fits the model's actual max sequence length, writes to a versioned model/config-specific Chroma collection, checks collection count and complete ID set after reopening, then runs **researcher-authored document-navigation probes**. The documented defaults are **384 content tokens, 64 overlap, 8 reserved special tokens**, subject to the loaded model's max sequence length. Smaller-token models require smaller values via command-line flags. `--legacy-parent-chunks` exists solely for reproducibility comparisons; they may truncate.

ChromaDB success is only a technical index/search proof. The original 30 navigation probes are researcher-authored, some include guideline names, and their scores are not expert-labelled S.4/S.5 assessment performance.

## Workstation run

On Windows, in project root with Python 3.11 or 3.12:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[vector,models,dev,experiment]"
python scripts/audit_regulatory_page_citations.py --root .
python scripts/run_native_bge_chroma_validation.py --root . --model BAAI/bge-large-en-v1.5 --window-tokens 384 --overlap-tokens 64 --out validation/v1.1_NATIVE_CHROMA_BGE_RESULTS.json
```

Or use: `powershell -ExecutionPolicy Bypass -File scripts/validate_v11_windows.ps1 -InstallDependencies`. On systems with an offline cached HF model, add `-OfflineModels` after installing dependencies. Check the JSON result, rather than assuming a shell command executed successfully. Expected successful report: `status=PASS_TECHNICAL_NATIVE_RUN`, `persistence_check=PASS_REOPEN_AND_IDS`, source count 15, source hashes verified, and zero over-length **rechunked** passages. The index's number of chunks can differ from 554 because token-aligned splitting is intentionally more conservative.

## Explicit remaining gates

1. Native ChromaDB + BGE execution on the user's hardware, including CPU/GPU memory, latency and persistence measurements.
2. Authorised, edition-verified pharmacopoeial monographs with source rights/reviewer attestation; no automatic promotion of the 7,064-document quarantine corpus.
3. M5 expert-labelled retrieval relevance and S.4/S.5 findings; M4 independent A–D evaluation, uncertainty and error analysis.
4. M1 live workflow and M3 real dossier ingestion interface (current stubs/fixtures are not the team's actual components).
5. Approved controlled pilot with assessors, audit and human gate. No autonomous medicine approval.

## Handover to Claude

Copy this package in full, retain `regulatory_sources/` and `artifacts/` separate from incoming monographs, rerun the original-page audit, then run the native model pipeline and inspect its report. Never treat `validation/v1.1_NATIVE_PREFLIGHT.json` as a successful ChromaDB/BGE test. For further data, follow `docs/CLAUDE_REVIEWED_DATA_CONTINUATION_v1.0.md`; do not downgrade source governance or reuse the exploratory compendial DB as approved authority.
