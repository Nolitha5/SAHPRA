"""Version-aware pharmacopoeial metadata discovery and guarded local monograph import.

Discovery links are NOT evidence. A locally imported PDF is not an applicable
standard until a reviewer attests rights, edition, provenance and case relevance.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

from pydantic import BaseModel, Field, ConfigDict, model_validator

from .chunking import chunks_from_pdf
from .registry import SourceRegistry, file_sha256
from .schemas import SourceRecord, SourceType


class PharmacopeialEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    kind: str
    title: str
    substance: str | None = None
    aliases: list[str] = Field(default_factory=list)
    cas: str | None = None
    ctd_sections: list[str] = Field(default_factory=list)
    publisher: str
    compendium: str
    edition_claim: str
    online_url: str
    pdf_url: str | None = None
    pdf_download_status: str
    scope: str
    content_included: bool = False
    review_flags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def source_rules(self):
        if urlparse(self.online_url).hostname not in {"digicollections.net", "www.digicollections.net"}:
            raise ValueError("Untrusted pharmacopoeial catalogue host")
        if self.pdf_url and urlparse(self.pdf_url).hostname not in {"digicollections.net", "www.digicollections.net"}:
            raise ValueError("Untrusted pharmacopoeial PDF host")
        if self.kind not in {"API_MONOGRAPH", "GENERAL_NOTICE"}:
            raise ValueError("Unsupported compendial category")
        return self


@dataclass(frozen=True)
class MatchResult:
    status: str
    candidates: list[dict[str, Any]]
    human_review_required: bool = True
    caution: str = "Catalogue match does NOT establish an applicable or complied-with regulatory standard."


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").casefold()).strip()


class PharmacopoeiaCatalogue:
    def __init__(self, entries: list[PharmacopeialEntry]):
        self.entries = entries
        keys = [e.id for e in entries]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate monograph identifiers")
        self.by_id = {e.id: e for e in entries}

    @classmethod
    def load(cls, path: Path | str) -> "PharmacopoeiaCatalogue":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls([PharmacopeialEntry.model_validate(e) for e in data["entries"]])

    def resolve(self, substance: str, *, cas: str | None = None, ctd_section: str = "3.2.S.4", kind: str = "API_MONOGRAPH") -> MatchResult:
        """Discovery only. Never returns regulatory evidence or compliance verdicts."""
        needle = norm(substance)
        if not needle and not cas:
            return MatchResult("NO_IDENTIFIER", [])
        matches = []
        for entry in self.entries:
            if entry.kind != kind:
                continue
            if ctd_section and not any(ctd_section.upper().startswith(x.upper()) for x in entry.ctd_sections):
                continue
            names = {norm(entry.substance or ""), *(norm(a) for a in entry.aliases)}
            match_by_name = bool(needle) and needle in names
            match_by_cas = bool(cas) and cas.strip() == entry.cas
            if not (match_by_name or match_by_cas):
                continue
            # Two supplied identifiers disagree with the source identity: no confident match.
            contradictory = bool(cas and entry.cas and cas.strip() != entry.cas and match_by_name)
            matches.append({"id": entry.id, "title": entry.title, "kind": entry.kind,
                            "online_url": entry.online_url, "edition_claim": entry.edition_claim,
                            "metadata_only": True, "content_indexed": False,
                            "matched_by": "CAS" if match_by_cas else "NAME",
                            "identifier_conflict": contradictory, "review_flags": entry.review_flags})
        if not matches:
            return MatchResult("NOT_FOUND", [])
        if any(x["identifier_conflict"] for x in matches):
            return MatchResult("IDENTIFIER_CONFLICT", matches)
        if len(matches) > 1:
            return MatchResult("AMBIGUOUS", matches)
        return MatchResult("REFERENCE_ONLY_REVIEW_REQUIRED", matches)


def collect_status(catalogue: PharmacopoeiaCatalogue, folder: Path) -> dict[str, Any]:
    """Presence in the catalogue is NOT represented as an acquired or indexed PDF."""
    rows = []
    for entry in catalogue.entries:
        path = folder / f"{entry.id}.pdf"
        present = path.exists()
        rows.append({"id": entry.id, "kind": entry.kind,
                     "online_reference": entry.online_url,
                     "pdf_present": present,
                     "pdf_sha256": file_sha256(path) if present else None,
                     "status": "DOWNLOADED_PENDING_REVIEW" if present else "REFERENCE_ONLY_NOT_ACQUIRED",
                     "approved": False})
    return {"entries": rows, "present_pdf_count": sum(x["pdf_present"] for x in rows),
            "indexed_pdf_count": 0, "expert_approved_count": 0,
            "message": "No status here asserts legal applicability, permissions, or verified regulatory compliance."}


def acquire_pdf(entry: PharmacopeialEntry, output_dir: Path, *, session=None) -> dict[str, str]:
    """Download only the catalogue's explicit PDF URL. No crawling or access bypass."""
    if not entry.pdf_url:
        raise ValueError("PDF URL not verified; use the official web page and supply a PDF manually")
    if urlparse(entry.pdf_url).hostname not in {"digicollections.net", "www.digicollections.net"}:
        raise ValueError("Untrusted host")
    import requests
    sender = session if session is not None else requests.Session()
    response = sender.get(entry.pdf_url, timeout=35, allow_redirects=True)
    response.raise_for_status()
    if urlparse(response.url).hostname not in {"digicollections.net", "www.digicollections.net"}:
        raise ValueError("Redirect to untrusted host blocked")
    payload = response.content
    if len(payload) < 1000 or not payload.startswith(b"%PDF-"):
        raise ValueError("Publisher did not return an intact PDF")
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"{entry.id}.pdf"
    if target.exists():
        raise FileExistsError("Existing PDF cannot be overwritten; preserve provenance")
    target.write_bytes(payload)
    return {"id": entry.id, "status": "DOWNLOADED_PENDING_REVIEW", "path": str(target),
            "sha256": hashlib.sha256(payload).hexdigest(), "source_url": response.url}


def import_verified_monograph(*, entry: PharmacopeialEntry, pdf_path: Path,
                              output: Path, approved_edition: str, reviewer_id: str,
                              rights_attestation: str, applicability_attestation: str,
                              edition_verification_note: str,
                              effective_from: date | None = None, effective_to: date | None = None,
                              chunk_size: int = 256, chunk_overlap: int = 48,
                              tokenizer=None) -> dict[str, Any]:
    """Human-attested, section-anchored local import with separate registries.

    Attestations are user assertions; the script cannot verify professional status
    or copyright. Requires strong explicit input and hashes PDF; never mixes
    the reference-only catalogue with actual regulatory evidence.
    """
    pdf_path = Path(pdf_path)
    if entry.kind != "API_MONOGRAPH":
        raise ValueError("General notices need separate verified PDF acquisition/import workflow")
    required = {"edition": approved_edition, "reviewer": reviewer_id,
                "rights": rights_attestation, "applicability": applicability_attestation,
                "edition_note": edition_verification_note}
    if any(len((v or "").strip()) < 12 for v in required.values()):
        raise ValueError("Explicit reviewer, edition, rights, provenance, and applicability attestations required")
    if not pdf_path.is_file() or pdf_path.read_bytes()[:5] != b"%PDF-":
        raise ValueError("Valid local PDF required")
    if entry.review_flags and "EDITION" in " ".join(entry.review_flags):
        if not re.search(r"(?:^|\b)(?:resolved\s+in|resolved:|confirmed\s+edition|verified\s+against)", edition_verification_note.casefold()) or "not resolved" in edition_verification_note.casefold():
            raise ValueError("Resolve the online/PDF edition discrepancy before import")
    import fitz
    with fitz.open(pdf_path) as pdf:
        first_pages = " ".join(p.get_text(sort=True) for p in list(pdf)[:2])
    if norm(entry.substance or "") not in norm(first_pages):
        raise ValueError("PDF does not contain the expected monograph identity on its first pages")
    digest = file_sha256(pdf_path)
    chunks = chunks_from_pdf(str(pdf_path), entry.id, size=chunk_size, overlap=chunk_overlap,
                             default_section=f"Ph.Int./{entry.id}", tokenizer=tokenizer)
    if not chunks:
        raise ValueError("No extractable page-anchored text; OCR required")
    src = SourceRecord(source_id=entry.id, authority="WHO Ph.Int.", title=entry.title,
                       document_code=f"Ph.Int.:{entry.id}", version=approved_edition,
                       effective_from=effective_from, effective_to=effective_to,
                       url=entry.online_url, license_note=rights_attestation,
                       source_type=SourceType.REGULATORY, approved=True,
                       sha256=digest, provenance_verified=True,
                       notes="Review attested, not independently checked: " + applicability_attestation)
    output.mkdir(parents=True, exist_ok=True)
    destination_pdf = output / "source_pdfs" / f"{entry.id}-{digest[:12]}.pdf"
    destination_pdf.parent.mkdir(parents=True, exist_ok=True)
    if not destination_pdf.exists():
        shutil.copyfile(pdf_path, destination_pdf)
    registry_path = output / "phint_approved_sources.json"
    reg = SourceRegistry.load(registry_path)
    reg.register(src)
    chunk_file = output / f"{entry.id}.jsonl"
    # Avoid partial writes when a same-ID file exists.
    if chunk_file.exists():
        raise FileExistsError("Already imported; never silently overwrite regulatory evidence")
    import os
    tmp = chunk_file.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for c in chunks:
            c.metadata.update({"compendium": "Ph.Int.", "monograph_id": entry.id,
                "substance": entry.substance or "", "cas": entry.cas or "",
                "material_scope": entry.scope, "approval_basis": "human_attestation",
                "original_pdf_page": c.page or 0})
            f.write(c.model_dump_json() + "\n")
    os.replace(tmp, chunk_file)
    reg.save(registry_path)
    note = {"monograph_id": entry.id, "sha256": digest, "pdf_pages": len({c.page for c in chunks}),
            "chunk_count": len(chunks), "approved_edition": approved_edition,
            "effective_from": effective_from.isoformat() if effective_from else None,
            "reviewer_id": reviewer_id, "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
            "rights_attestation": rights_attestation,
            "applicability_attestation": applicability_attestation,
            "edition_verification_note": edition_verification_note,
            "source_url": entry.online_url, "retained_pdf": str(destination_pdf), "reviewer_credentials_independently_verified": False,
            "warning": "Regulatory applicability, permissions and reviewer identity remain assertions until externally verified."}
    (output / f"{entry.id}.review.json").write_text(json.dumps(note, indent=2), encoding="utf-8")
    return note
