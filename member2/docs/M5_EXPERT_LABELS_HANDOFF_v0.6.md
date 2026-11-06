# Handoff to Member 5 — Expert Regulatory Ground Truth (NOT YET RECEIVED)

The 30 queries in `examples/researcher_navigation_probes_v0.6.json` are **engineering navigation tests** written by the software team, NOT expert-labelled query–passage pairs. Do **not** reuse their expected source labels as expert answers without independent review.

## Expert assessment data needed

For each blinded regulatory question, independently record:

- `query_id`, `question`, `ctd_subsection` (e.g. `3.2.S.4.3`), `dossier_type` and submission/applicability date.
- `relevant_passages`: one or more anchors `{source_id, source_pdf_sha256, section, pdf_page, exact_text_span, relevance_grade}`; explicitly allow multiple sources and pages per question.
- `applicability_rationale`: why the source version and jurisdiction apply, including biological versus chemical substance scope.
- `no_applicable_evidence`: whether the accepted corpus has no relevant passage. These questions are essential for evaluating honest insufficiency.
- `reviewer_id`, `review_timestamp`, `adjudication` and `independent_second_review`, where feasible.
- Reference extraction/answer claims and acceptable assessor findings for S.4.1 through S.4.5.
- Citation faithfulness label and any contradictory/obsolete evidence flag.

A separate evaluation holdout must not be used to tune embedding, chunking or reranking configurations. Prevent identical passages/near-duplicate questions from leaking across development and holdout sets.

## Steps after labels arrive

1. Verify that each evidence reference matches one of the 15 corpus source hashes and that its exact text is present on the cited original PDF page.
2. Freeze the input, grader and labels; define per-class uncertainty/insufficiency and evaluability rules before running final experiments.
3. Run model-specific tokenized chunking, BGE indexing and reranking experiments across fixed held-out queries.
4. Compute properly defined graded Recall@K, MRR, nDCG and evidence faithfulness, plus error-analysis categories.
5. Evaluate S.4 provisional findings with precision, recall and missed-deficiency rates; document denominator and cases requiring human adjudication.
6. Provide the results to M4's full A–D comparison harness; M1 integrates the application and M5 authorizes human-assessment protocol.

The user-supplied source collection is not yet approved for live regulatory decisions. The SAHPRA v8/v9 internal header conflict must be independently resolved.
