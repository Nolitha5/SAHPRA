# Regulatory source governance and local source onboarding

## Required corpus categories (from M2 spec)

- ICH M4Q, Q11, Q6A, Q3A
- WHO TRS 1010 Annex 10 (2018) and other relevant WHO guidance if approved
- SAHPRA guidelines relevant to Module 3.2.S
- Applicable pharmacopoeial monographs (BP, USP, Ph.Eur., IP, as authorized)
- Key peer-reviewed literature if approved, **registered as `source_type=literature`** and excluded from normal regulatory retrieval unless explicitly requested as non-authoritative context

**Candidate additional sources:** ICH Q2(R2), ICH Q14 and other analytically relevant documents are not automatically in the original named M2 list; M5/domain lead should approve their applicability. Official WHO TRS 1010 Annex 10 landing page: https://www.who.int/publications/m/item/trs1010-annex10 . Official ICH guideline directory: https://www.ich.org/page/quality-guidelines . Official SAHPRA site: https://www.sahpra.org.za/ . These are navigation links, not declarations of source edition, effective date, or reuse licence.

## Source admission checklist

1. Verify official publisher and exact original document (not arbitrary copied secondary webpages).
2. Record authority, code, full title, edition/revision, publication/effective/supersession dates, official URL and source hash. Do not infer date from website's crawl timestamp.
3. Verify source access and indexing permission, particularly for licensed pharmacopoeia texts.
4. Record product/jurisdiction-specific applicability rules with expert review.
5. Register using immutable versioned `source_id`; NEVER replace source contents under the same ID.
6. Only set `approved=true` and `provenance_verified=true` when these steps are performed. An unapproved record is non-searchable.
7. Retain original PDF outside Git in ignored `regulatory_sources/`; rename as `<source_id>.pdf`. The registry optionally pins SHA-256.
8. Use the local OCR/structure pipeline from M3 if text extraction fails; do not index empty scanned pages.
9. Test exact citation locations and extraction quality on samples before using a document for assessment.

## Effective dates and S.5 standards

When `effective_on` is specified, a source lacking verified effective date is NOT returned as historically applicable. This prevents the system asserting a monograph edition was current without proof. Multiple editions should receive distinct source IDs with non-overlapping effective windows when possible. Apparent overlaps/conflicts require human review.

## Sensitive dossier handling

Sponsor content is case-specific. The RKB `M2Runtime.index()` rejects `SourceType.SPONSOR`, and the service does not persist raw dossier text for reuse. M3 must de-identify/handle confidentiality before passing a case to S.4. M4 stores case state and audit within the approved environment. No external model calls are enabled by default.

## Non-bundled assets

The ZIP includes **no actual ICH/SAHPRA/WHO/USP/BP/Ph.Eur. text**. This deliberately avoids claiming unverified content is authoritative or redistributing licensed materials. Tier-0 real-rule verification and research-grade metrics require the team's approved actual corpus. The synthetic fixtures in `examples/` are conspicuously `TEST_ONLY` and locked out of research mode.
