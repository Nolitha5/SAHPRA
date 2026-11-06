# Pilot on public ICH guidelines (before Member 3's data)

`scripts/pdf_to_jsonl.py` is a **temporary stand-in** for Member 3's ingestion pipeline. It turns text-based PDFs into passages in the same JSONL format Member 3 will deliver, so you can test retrieval and run a first benchmark on real regulatory text.

It does **not** do OCR, table extraction or automatic CTD mapping. Those stay with Member 3. When their data arrives, load it the same way and stop using this script.

All commands run from the `member2-rag` folder with the environment active:

```powershell
cd "C:\Users\4IR Research Lab\Downloads\qa-rag-member2\qa-rag-member2\member2-rag"
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt        # adds pypdf
```

## 1. Download the PDFs

From **ich.org → Quality Guidelines**, download the guidelines you need and save them in `data\raw\` (create the folder; git ignores it). Suggested set for S.4 work:

| File name to use | Guideline | Default CTD section |
|---|---|---|
| `ICH_Q6A.pdf` | Q6A: Specifications | 3.2.S.4 |
| `ICH_Q2R2.pdf` | Q2(R2): Validation of Analytical Procedures | 3.2.S.4.3 |
| `ICH_Q3A_R2.pdf` | Q3A(R2): Impurities in New Drug Substances | 3.2.S.3 |
| `ICH_Q11.pdf` | Q11: Development and Manufacture of Drug Substances | 3.2.S |

Use the **Step 4 / final** versions, not drafts.

## 2. Fill in the manifest

```powershell
copy examples\ich_manifest.example.json data\raw\manifest.json
```

Open `data\raw\manifest.json` and, for each document:

* replace every `FILL IN` with the version and date **printed on that PDF's cover page** (the script refuses to run while any `FILL IN` remains). If the PDF doesn't state something, delete that line rather than guessing;
* check the title against the cover page;
* optional: set `first_page` to skip the cover and table of contents, and `last_page` to skip references or annexes;
* optional: tag pages more precisely with `page_sections`, for example `"page_sections": "5-9:3.2.S.4.1,10-14:3.2.S.4.5"`. Pages you don't list use `ctd_section`.

## 3. Convert at two chunk sizes

```powershell
python scripts/pdf_to_jsonl.py --manifest data/raw/manifest.json --output data/processed/ich_w300.jsonl --chunk-size 300 --overlap 50
python scripts/pdf_to_jsonl.py --manifest data/raw/manifest.json --output data/processed/ich_w150.jsonl --chunk-size 150 --overlap 30
```

Each run prints a report per PDF. Check:

* `pages_without_text`: pages that are scanned images. They are skipped, not guessed; mention them to Member 3.
* `header_footer_lines_removed`: repeated headers and page numbers taken out.
* `chunks`: how many passages were made.

Chunk size is in **words** (300 words ≈ 400 tokens, within BGE's 512-token limit).

## 4. Load each chunk size into its own collection

One collection per embedding model and chunk size (a collection is pinned to the model that built it):

```powershell
# bge-large (project default model, ~1.3 GB)
python scripts/load_documents.py --input data/processed/ich_w300.jsonl --collection ich_large_w300 --embedding-model BAAI/bge-large-en-v1.5
python scripts/load_documents.py --input data/processed/ich_w150.jsonl --collection ich_large_w150 --embedding-model BAAI/bge-large-en-v1.5
# bge-small (comparison / low-resource laptops)
python scripts/load_documents.py --input data/processed/ich_w300.jsonl --collection ich_small_w300 --embedding-model BAAI/bge-small-en-v1.5
python scripts/load_documents.py --input data/processed/ich_w150.jsonl --collection ich_small_w150 --embedding-model BAAI/bge-small-en-v1.5
```

To use one of them in the dashboard or the scripts, set in `.env` (the default pilot setup):

```
M2_EMBEDDING_MODEL=BAAI/bge-large-en-v1.5
M2_COLLECTION_NAME=ich_large_w300
```

and restart `python -m app.api`.

## 5. Try real questions

```powershell
python scripts/search.py "Which validation characteristics apply to an assay procedure?" --section 3.2.S.4.3
python scripts/run_agent.py evidence --section 3.2.S.4.1 --question "What tests are normally included in a drug substance specification?"
```

Check every answer against the PDF page it cites. That's how you learn whether retrieval is working.

## 6. Write pilot benchmark questions

Write 15–20 questions in `benchmarks/pilot.jsonl`, one per line. For each, open the PDF, find the page that answers it, and record that page:

```json
{"question_id": "P001", "question": "Which validation characteristics apply to an assay procedure?", "ctd_section": "3.2.S.4.3", "relevant_pages": [{"source_identifier": "ICH Q2(R2)", "page_number": 0}], "labelled_by": "Member 2 pilot (not expert-verified)", "expert_notes": "Replace page_number 0 with the real page"}
```

* `source_identifier` must match the manifest exactly (for example `ICH Q2(R2)`).
* Page numbers are the **PDF page** (as your PDF viewer counts them), not the number printed on the page.
* Don't copy sentences from the PDF into the question; that would make the test too easy (the benchmark warns you if it finds a question word-for-word in the index).
* Page-level labels are used because they stay valid for every chunk size.

## 7. Run the pilot benchmark

`benchmarks/pilot.jsonl` already contains 20 draft questions (P001–P020) with page labels checked
against the page text. They are marked `"labelled_by": "Member 2 pilot draft (AI-assisted, not
expert-verified)"`: review each one against the PDF before relying on the numbers, and add your own.

```powershell
pip install -r requirements-eval.txt   # once, for --ragas
python scripts/evaluate_retrieval.py --benchmark benchmarks/pilot.jsonl --configs benchmarks/configs.pilot.json --ragas
```

This compares, on the same questions (all five comparisons from the project brief):

| Config | What it shows |
|---|---|
| `large_w300_dense_only` vs `large_w300_reranked` | what the reranker adds |
| `large_w300_reranked` vs `large_w300_reranked_no_filter` | what the CTD filter adds |
| `large_w300_reranked` vs `large_w150_reranked` | effect of chunk size (300 vs 150 words) |
| `large_w300_reranked` vs `small_w300_reranked` | bge-large vs bge-small |
| `small_*` rows | the same comparisons for the low-resource model |

Results are saved in `results\` and appear on the dashboard's Benchmark tab.

## Reporting honestly

Call these **pilot results**: a small set of public ICH guidelines, a temporary converter, and questions labelled by you rather than an expert. They show the method works and give first comparisons; the final results come from Member 3's corpus and Member 5's expert labels.
