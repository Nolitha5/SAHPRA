# Contract handoff — M1, M2, M3, M4, M5

## API endpoint

`POST /m2/phint/evidence`, on the existing M2 FastAPI router. Configure `M2_PHINT_CATALOGUE=<absolute path to pharmacopoeia/WHO_PHINT_RESEARCH_CATALOGUE_v0.7.json>`. Mount M2 router inside M1's orchestration runtime. Research mode uses the same required M2 service token as other routes.

Illustrative request (not an actual approval workflow):

```json
{
  "substance": "Paracetamol",
  "cas": "103-90-2",
  "question": "What indexed evidence addresses identity and assay?",
  "requesting_agent": "S4_CONTROL",
  "as_of": null
}
```

Expected output *before* monograph import:

```json
{
  "lookup_status": "MONOGRAPH_REFERENCE_ONLY_NOT_INDEXED_OR_APPROVED",
  "human_review_required": true,
  "evidence": [],
  "regulatory_approval_or_rejection": null
}
```

Other fields contain the official reference URL, metadata and a caution. A real response will not become `RETRIEVAL_FOUND` until a corresponding, reviewed/registered monograph is indexed. If `as_of` is given but no effective-from date is verified, return `EFFECTIVE_DATE_NOT_VERIFIED`.

## Required M3 handoff

Dossier (not regulation) claims: `case_id`, `drug_substance`, `cas`, `CTD section`, `sponsor claimed compendium`, `sponsor claimed edition`, `submission_date`, structured S.4 specifications/methods/batch analyses, PDF/page/chunk source anchors. Missing CAS or uncertain synonym requires human review.

## Required M5 decisions

Reviewer-approved PDF/source bytes, rights for text extraction/local indexing, exact edition, applicability to the individual submission, effective date and historical comparison, applicable general chapters, approved labelled query/evidence pairs. A general monograph does not replace assay data or pharmacopoeial references.

## M4 evaluation and traceability

Test three distinct failure families: (1) false monograph identity/mismatched CAS, (2) source absent or outdated/undetermined edition, (3) correct source but irrelevant passage. Measure passage relevance only on gold labels from real domain assessors. The reference-only match must never be counted as a correct retrieved passage. No autonomous drug-approval decision is returned anywhere by M2.
