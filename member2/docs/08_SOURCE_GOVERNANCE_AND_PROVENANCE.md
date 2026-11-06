# Source Governance and Provenance
**Version:** 1.2 | **Date:** 2026-10-28

---

## 1. Provenance Record Fields

Every registered source carries:

| Field | Description |
|-------|-------------|
| `source_id` | Stable unique identifier (e.g., `ICH-Q11`) |
| `authority` | Issuing body (e.g., `ICH`, `SAHPRA`, `WHO`) |
| `title` | Full document title |
| `document_code` | Official code (e.g., `Q11`, `M4Q`) |
| `version` | Edition/revision string |
| `publication_date` | Original publication date |
| `effective_from` | Date from which applicable |
| `effective_to` | Date after which superseded (null if current) |
| `url` | Publisher URL (informational) |
| `license_note` | Licence constraints |
| `source_type` | REGULATORY / SYNTHETIC / LITERATURE / SPONSOR |
| `approved` | Explicit true/false — never defaults to approved |
| `sha256` | SHA-256 of the physical PDF file |
| `provenance_verified` | Confirmed match between file and registered hash |
| `notes` | Free-text governance notes |

---

## 2. Approval Workflow

```
New PDF arrives in pharmacopoeia/incoming/
          ↓
Reviewer calculates SHA-256
          ↓
Registry.register() called with approved=False, provenance_verified=False
          ↓
Human reviewer confirms:
  - Publisher identity
  - Document version
  - Effective dates
  - Licence rights
  - PDF integrity (SHA-256 matches)
          ↓
registry.records[source_id].approved = True
registry.records[source_id].provenance_verified = True
registry.save(path)
          ↓
Source becomes eligible for retrieval
```

**A source with `approved=False` or `provenance_verified=False` is never returned by `EvidenceService.retrieve()`.**

---

## 3. Governance Flags on Current Sources

| Source | Governance Flag |
|--------|----------------|
| SAHPRA PEM-02 | Cover page says v8; content references v9. Mandatory independent version review before citing in regulatory decisions. |
| ICH Q6B | Biologics-only scope. Must not be applied to small-molecule drug substances without product-scope filter. |
| WHO TRS 1010 A10 | Available and verified; WHO download was DNS-blocked in container; file supplied by user and hash-verified. |

---

## 4. Pharmacopoeial Source Controls

Pharmacopoeial monographs (BP, EP, Ph.Int) require additional controls:

- `rights_status` — must be `OPEN_ACCESS` or `INSTITUTIONAL_LICENCE`
- `review_status` — must be `APPROVED` before promotion out of quarantine
- `applicable_jurisdictions` — list of regulatory systems where the monograph is recognised
- `edition` and `effective_date` — must be recorded exactly

**Draft, mirrored or unidentified monographs are never auto-promoted to the approved collection.**

---

## 5. Quarantine Collection

Pharmacopoeial sources under review are isolated in a separate `research/unverified` collection.
They may be retrieved in research mode (`allow_synthetic=True`) but not in production mode.

---

## 6. Integrity Verification

```powershell
# Verify all source hashes
python -c "
from pathlib import Path
from m2.registry import file_sha256
import json
manifest = json.loads(Path('regulatory_sources/UNIQUE_PDF_INTEGRITY_MANIFEST_v0.5.json').read_text())
for src in manifest['sources']:
    p = Path('regulatory_sources') / src['filename']
    if p.exists():
        actual = file_sha256(p)
        expected = src['sha256']
        print(src['source_id'], 'OK' if actual == expected else f'MISMATCH: {actual} vs {expected}')
    else:
        print(src['source_id'], 'FILE MISSING')
"
```
