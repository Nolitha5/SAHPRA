# v0.9 — Supplied compendial archives and IPRP assessor guidance

## What was received

The research team supplied fourteen ZIP archives and the document **IPRP QWGG Guidance for Quality Assessors – Drug Substance**, version 1.1 (20 September 2018). The ZIP collections include:

- Mirrored British Pharmacopoeia HTML monographs, formulated products, herbal drugs, preliminary pages and General Notices. Several pages identify **BP 2024 (Ph. Eur. 11.3 update)**; the mirror URL is not itself evidence of authorised access or an official current edition.
- European Pharmacopoeia 11.0 monograph and analytical-method PDF extracts in multiple separately packaged archives. These are extract copies with no independently demonstrated publisher chain of custody or edition applicability.
- A mixed **General.zip** collection of general drug-product and pharmaceutical-test PDFs plus an unrelated `.db` file. Non-PDF/HTML content is excluded, and the collection is not automatically designated as USP.

These are user-supplied research materials, not automatically approved regulatory evidence. The four desired **WHO International Pharmacopoeia API monographs** are *not* thereby acquired, regardless of overlapping substance names. Never relabel BP/Ph. Eur. material as WHO Ph.Int.

## Integration policy

1. Keep the existing 15-reference official-guidance collection and current Evidence/RERA code unchanged.
2. Process the supplemental archives only into `artifacts/quarantine/compendial_discovery.sqlite3` as an **isolated full-text research/discovery index**. The index requires an explicit research-only opt-in before exposing excerpts.
3. Never include unapproved extracts in the authoritative RKB or S.4 compliance decision path. These are *candidate sources*, and their source origin, edition, effective date, licence, geographic applicability and substance identity require review.
4. The IPRP document is a useful **nonbinding assessment model**, explicitly limited to chemical drug substances. It is not a substitute for SAHPRA/ICH regulatory requirements. Its S.4 and S.5 checklist prompts are not automatic requirements or pass/fail rules.
5. Never infer missing numeric compendial limits or chemically approve a molecule. Qualified assessors remain responsible for evaluation and final regulatory decisions.
6. Keep case-specific sponsor data, regulatory guidance, extracted compendial references and operational audit/memory logically separate.

## How to use

Obtain this v0.9 project ZIP and keep the original fourteen uploaded ZIPs separately. For the entire local archive build, place/copy the original archive files to `data/external_archives/` inside your extracted project, or point `--archive-dir` to a directory that contains them. Their filenames must remain intact.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python scripts/manage_compendia_archives.py inventory --archive-dir data/external_archives
python scripts/manage_compendia_archives.py build --archive-dir data/external_archives --db artifacts/quarantine/compendial_discovery.sqlite3
python scripts/manage_compendia_archives.py search --db artifacts/quarantine/compendial_discovery.sqlite3 --query Ibuprofen --research-only
python scripts/demo_compendial_s4_handoff.py --db artifacts/quarantine/compendial_discovery.sqlite3 --substance Ibuprofen
python -m pytest -q
```

The package can include an **already built offline discovery index**. No native ChromaDB/BGE model runs are claimed by that fact. When permissions and approvals are obtained, use the already-implemented source import and native BGE+Chroma runners to construct an **approved, separately versioned** retrieval index. Do not feed the quarantine index directly into the regulatory `Evidence/RERA` endpoint.

## Planned M1/M3/M4/M5 handoffs

- **M1 orchestration:** continue using the existing `/m2/evidence` and `/m2/s4/review` contracts. Compendial discovery is an optional, research-only capability and should never be interpreted as approved evidence.
- **M3 document processing:** pass structured sponsor dossier evidence with exact CTD subsection and page anchors, and retain the original extracted table structures.
- **M4 evaluation/audit:** log provenance and approval state, evaluate insufficient-evidence and wrong-edition cases, avoid using synthetic labels as expert decisions.
- **M5 QA/S.5:** review edition, monograph applicability, reference-standard identity, rights, and source reliability; review IPRP checklist prompts and enter actual expert judgements.

## Remaining dependencies

- No expert-reviewed applicability attestation yet for the new extracted compendial materials.
- No proof of licence for use/redistribution in an AI database of mirrored BP or extracted Ph. Eur. material.
- The 4 WHO Ph.Int. monographs identified in v0.8 have not been provided as official WHO PDFs; these archive extracts do not replace them.
- Native BGE/Chroma indexing and authoritative corpus retrieval benchmarking still require a dependency-enabled workstation.
- Any actual S.4/S.5 regulatory case evaluation requires genuine qualified assessor review, supporting dossiers and governance approval.
