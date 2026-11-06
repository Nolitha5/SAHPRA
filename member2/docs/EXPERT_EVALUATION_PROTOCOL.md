# Expert-labelled retrieval evaluation — M2 ↔ M5 ↔ M4

## Research status
No expert-labelled gold records, adjudicated reviewer judgments, or signed expert approvals were available in this session. The benchmark code and a draft label template are supplied, **not** completed expert evaluation results.

## Label design
- M5 defines a stratified set of real regulatory questions covering S.1–S.7 and the S.4 sub-sections, authority/version filters, negative cases and ambiguous queries.
- Experts identify **source-anchored** relevant evidence by `source_id + section + page`; chunk IDs are not fixed because 256/512/1024-token trials change chunk boundaries.
- A negative/no-evidence benchmark should be tracked separately from positive retrieval metrics, with abstention correctness, false-source rate and failure type.
- Experts record domain rationale, source version applicability, adjudication status and reviewer identity under project data governance.
- Source PDFs and SHA-256 must match the registry. Reviewers cannot select documents that were not acquired and verified.
- M4 owns full-system evaluation; M2 supplies per-query retrieval rankings, metrics, configs, runtime latencies, source provenance and error breakdowns. M5 owns ground truth and qualifications.

## Draft expert-label document
Template: `docs/templates/EXPERT_LABELS_DRAFT.json`. It is not validated. Import and gate using:

```powershell
python -c "from m2.label_governance import assess_labels; print(assess_labels('regulatory_sources/expert_labels.json','local_indexes/sources.json','regulatory_sources'))"
```

`NOT_EXPERT_VERIFIED` means do not publish a claim of expert evaluation. `ATTESTED_WITH_SOURCE_VERIFICATION` means reviewers are named, two approved review records exist, and all source hashes/pages match. It **does not establish** their credentials or independence; those require independent human verification.

## Experiments
Use `scripts/run_real_grid.py` and real approved PDFs and a fixed actual tokenizer. It evaluates three candidate embedding models, three chunk sizes, overlaps, and optional BGE reranking. Source anchors rather than chunk IDs prevent artificially incomparable relevance labels. All model names, sizes, hyperparameters, hashes, hardware and errors must be included in the thesis evidence package.

Do not treat Ragas LLM-judge scores as expert judgments. Faithfulness depends on the exact prompt and locally approved judge model. Predefine thresholds and negative-case evaluation with the research team before examining results.
