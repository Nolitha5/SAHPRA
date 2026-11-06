# Member 2 v1.0 — Deferred reviewed pharmacopoeia handoff and source onboarding

**Release:** v1.0 • **Scope:** technical readiness only • **Not a regulatory assessment product**

## Why this release exists

The expert-reviewed pharmacopoeial corpus has not yet been supplied. This release
continues implementing Member 2 without claiming approval of the unverified BP,
Ph. Eur. or other compendial extracts previously uploaded. It does NOT convert the
quarantine index into regulatory evidence, train/fine-tune a language model,
complete expert evaluation, or run an authorised pilot.

## Preserved evidence boundary

- Existing 15 user-supplied SAHPRA/ICH/WHO official-reference PDFs are retained.
  Their PDF SHA-256 checks pass (15/15), and the existing engineering preview
  index contains 554 page-anchored chunks. Expert adoption/applicability remains
  pending.
- Existing separately quarantined compendial FTS index retains 7,064 extracted
  documents and 13,524 passages. **None are approved regulatory evidence**.
- WHO monograph catalogue contains metadata-only links; the monograph PDFs
  cannot be assumed downloaded, licensed, edition-verified, or indexed.
- IPRP QWGG v1.1 quality-assessor guidance is NONBINDING model guidance for
  chemical substances; S.4/S.5 checklists are never automatic rule thresholds.

## New code

| File | Responsibility |
|---|---|
| `src/m2/deferred_handoff.py` | Strict sponsor claim model, WHO candidate resolution, nonbinding S.4.1–S.4.5/S.5 review checklists, explicit M1/M4/M5 status and data-gaps, sealed regulation evidence field |
| `src/m2/monograph_onboarding.py` | Official-host and PDF byte-hash validation, substance identity, edition/applicability/rights fields; **intake receipts only** |
| `src/m2/api.py` | `POST /m2/compendia/deferred-assessment` M1/M5 orchestration adapter |
| `scripts/run_deferred_s4_s5_handoff.py` | Repeatable four-case synthetic engineering run, optional metadata-only quarantine discovery |
| `scripts/stage_reviewed_monograph.py` | Future intake from an externally reviewed original PDF and review proposal |
| `examples/deferred_s4_s5_synthetic_cases.json` | Explicitly synthetic Paracetamol, Ibuprofen, Amoxicillin trihydrate, Metronidazole cases (not expert labels) |
| `examples/monograph_review_proposal_TEMPLATE.json` | Required future edition, origin, file hash, permissions, reviewer and scope fields |
| `tests/test_deferred_compendia_v10.py` | 15 new tests including M1/M5 API integration, identifier conflicts, non-approval, SHA checks and unverified-source isolation |

## How to run — cross-platform

From the extracted project root, using Python 3.11/3.12 where possible:

```bash
python -m pip install -e '.[dev]'
python scripts/run_deferred_s4_s5_handoff.py --root . --include-research-leads
python -m pytest -q -k 'not test_offline_benchmark_covers_all_sources_and_modes'
```

Omit `--include-research-leads` for the default **no-unverified-discovery** mode.
The optional switch exposes only references to quarantined material and will not
supply text passages, quantitative criteria, compliance labels, or citations.

Read `artifacts/deferred_handoff_v1.0/TECHNICAL_HANDOFF_REPORT.json` and individual
case reports. Outputs must be labelled **synthetic engineering**, not expert scores.

## M1/M5 integration

Configure the normal M2 router inside M1's existing FastAPI app and set:

```bash
M2_PHINT_CATALOGUE=pharmacopoeia/WHO_PHINT_RESEARCH_CATALOGUE_v0.7.json
```

In research mode M1 must also configure `M2_SERVICE_TOKEN` and provide the
`X-M2-Token` header, in addition to the group's authentication / authorisation.

Example call to `POST /m2/compendia/deferred-assessment`:

```json
{
  "case_id": "SYN-PARA-001", "drug_substance": "Paracetamol",
  "cas": "103-90-2", "product_type": "CHEMICAL",
  "claimed_compendium": "Ph.Int.", "claimed_edition": null,
  "s4_fields": {"3.2.S.4.1": {"compendial_claim": "Ph.Int."}},
  "s5_fields": {"reference_standard_source": "Not supplied"}
}
```

The handoff returns `qa_status=PENDING`, `regulatory_evidence=[]`, and
`drug_authorisation_decision=null` until separately proven evidence and human
reviews are supplied. M1 routes it, M4 audits it, and M5 reviews the source and
standard claims. Do not interpret a metadata-only match as an adopted standard.

## Future reviewed pharmacopoeial corpus (when provided)

1. Preserve the original approved source PDF separately; do not use a mirror
   extract to assert copyright, official edition or official publisher identity.
2. Ask M5/domain/regulatory lead to independently assess *licensing permission*,
   publisher origin, current/historical edition, effective dates, drug-substance
   type and SAHPRA adoption/applicability. Keep their attestation in governance.
3. Create a proposal JSON from
   `examples/monograph_review_proposal_TEMPLATE.json`, with actual SHA-256,
   source metadata and review references (not placeholder values).
4. Run:

   ```bash
   python scripts/stage_reviewed_monograph.py --proposal PATH_TO_PROPOSAL.json --pdf PATH_TO_PDF.pdf
   ```

   This checks integrity and identity. It **does not automatically add** the
   source to RERA's trusted collection, grant permission, or set an approved flag.
5. After genuine external approval, use the project's guarded source-curation and
   indexing facilities (`src/m2/curation.py`, `pharmacopoeia.import_verified_monograph`,
   `src/m2/registry.py`); adapt importer per compendium type/rights. Register a
   *versioned* `SourceRecord` tied to original PDF SHA-256, page and effective date.
6. Build a dedicated ChromaDB/BGE index, confirm persistence, citation fidelity,
   source-version filters and no cross-source leakage. Keep dossier/sponsor chunks
   and unverified discovery data logically separate.
7. M5 supplies real expert labels and citations; M4 runs the A–D evaluation harness;
   report Precision@K/Recall@K/nDCG and S.4/S.5 findings metrics only when expert
   labels and approved source applicability exist.
8. M1 integrates and controls the human gate. No autonomous SAHPRA approval.

## Native ChromaDB/BGE status

`validation/V1_0_NATIVE_PREFLIGHT.json` says **BLOCKED** in this execution
container: ChromaDB and Sentence Transformers cannot be installed due to lack
of package-index connectivity. The workstation runner is preserved:

```bash
python -m pip install -e '.[vector,models,dev]'
python scripts/run_native_bge_chroma_validation.py --root . --model BAAI/bge-large-en-v1.5
```

A passing local engineering check still does not mean expert validity.

## Test status

- 15 NEW synthetic/integration/security/gating tests pass.
- 128 suite tests pass when excluding a previously established and unchanged
  long-running full-corpus navigation benchmark; that one is NOT claimed rerun.
- All 15 present original guideline PDFs passed local SHA-256 integrity validation.
- Four cases were executed against catalogue and optional quarantine metadata;
  all 4 remain QA pending, 4/4 need human review, 0 autonomous authorisations,
  and 0 expert-sourced performance claims.
- Native ChromaDB/BGE and human pilot remain unexecuted in this environment.
