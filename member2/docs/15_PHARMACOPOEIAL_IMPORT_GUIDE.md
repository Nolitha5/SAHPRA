# Pharmacopoeial Import Guide
**Version:** 1.2 | **Date:** 2026-10-28

---

## 1. Import Location

Place all pharmacopoeial PDFs for review in:
```
pharmacopoeia/incoming/
```

Do not place files elsewhere. Files in `incoming/` are not indexed until manually reviewed and promoted.

---

## 2. Supported Sources

| Source | Publisher | Licence Required | Notes |
|--------|-----------|-----------------|-------|
| International Pharmacopoeia (Ph.Int) | WHO | Open access | Preferred; verify current edition |
| British Pharmacopoeia (BP) | MHRA | Institutional licence | Do not redistribute |
| European Pharmacopoeia (Ph.Eur) | EDQM | Institutional licence | Do not redistribute |

---

## 3. Substance Scope (Current Research)

| Substance | INN | CAS | Forms |
|-----------|-----|-----|-------|
| Valsartan | Valsartan | 137862-53-4 | Base |
| Amlodipine | Amlodipine | 88150-42-9 | Besylate common |
| Hydrochlorothiazide | Hydrochlorothiazide | 58-93-5 | — |

Always verify exact substance identity including salts, solvates and hydrates before indexing.

---

## 4. Import Workflow

```
Step 1: Obtain PDF from authorised publisher source
Step 2: Place in pharmacopoeia/incoming/
Step 3: Calculate SHA-256:
    python -c "from m2.registry import file_sha256; print(file_sha256('pharmacopoeia/incoming/yourfile.pdf'))"
Step 4: Human reviewer confirms:
    - Publisher identity (title page, header/footer)
    - Edition and effective date
    - Substance identity (INN, CAS, synonyms)
    - Licence terms
    - SHA-256 matches publisher hash (if available)
Step 5: Register using monograph_onboarding.py or directly via SourceRegistry
Step 6: Set approved=True and provenance_verified=True after review
Step 7: Rebuild index
```

---

## 5. Review Checklist

Before setting `approved=True`:

- [ ] Confirmed this is a genuine, official publication
- [ ] Publisher and edition verified (title page inspected)
- [ ] Effective date recorded and verified
- [ ] Substance identity confirmed (not a different salt or formulation)
- [ ] Licence rights noted; redistribution restrictions recorded
- [ ] SHA-256 calculated and recorded
- [ ] No draft, unofficial mirror or preprint
- [ ] No conflicting earlier version in the registry for the same substance

---

## 6. Governance Flags

Any ambiguity about identity, version or licence must be recorded as a `notes` value on the `SourceRecord` and the source must remain `approved=False` until the ambiguity is resolved.

---

## 7. Prohibition

Pharmacopoeial licensed text must NOT be included in release ZIP packages distributed outside the research team. Use only metadata (title, edition, date, CAS, SHA-256) in shared artefacts.
