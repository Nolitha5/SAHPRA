"""WHO Ph.Int. discovery, conservative acquisition, and attested local PDF import.

No copyright bypass, no scraping gated compendia, no auto-approval. Run --help.
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from m2.pharmacopoeia import PharmacopoeiaCatalogue, collect_status, acquire_pdf, import_verified_monograph

CATALOGUE = ROOT / "pharmacopoeia/WHO_PHINT_RESEARCH_CATALOGUE_v0.7.json"
PENDING = ROOT / "pharmacopoeia/acquired_pending_review"
APPROVED = ROOT / "pharmacopoeia/reviewed_local"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="Show online reference entries, not indexed passages")
    sub.add_parser("status", help="Show downloaded-vs-reference-only coverage")
    look = sub.add_parser("resolve", help="Find likely WHO monograph by substance/CAS")
    look.add_argument("--substance", default="")
    look.add_argument("--cas")
    look.add_argument("--ctd-section", default="3.2.S.4")
    acq = sub.add_parser("download", help="Download ONLY a verified WHO PDF, where the direct URL exists")
    acq.add_argument("--id", required=True)
    imp = sub.add_parser("import-reviewed", help="Human-attested local PDF import; does not verify credentials")
    imp.add_argument("--id", required=True)
    imp.add_argument("--pdf", required=True, type=Path)
    imp.add_argument("--edition", required=True)
    imp.add_argument("--reviewer", required=True)
    imp.add_argument("--rights-note", required=True)
    imp.add_argument("--applicability-note", required=True)
    imp.add_argument("--edition-note", required=True)
    imp.add_argument("--effective-from", type=date.fromisoformat)
    imp.add_argument("--effective-to", type=date.fromisoformat)
    args = p.parse_args()
    cat = PharmacopoeiaCatalogue.load(CATALOGUE)
    if args.command == "list":
        out = [e.model_dump() for e in cat.entries]
    elif args.command == "status":
        out = collect_status(cat, PENDING)
    elif args.command == "resolve":
        out = cat.resolve(args.substance, cas=args.cas, ctd_section=args.ctd_section).__dict__
    elif args.command == "download":
        out = acquire_pdf(cat.by_id[args.id], PENDING)
    elif args.command == "import-reviewed":
        out = import_verified_monograph(entry=cat.by_id[args.id], pdf_path=args.pdf,
            output=APPROVED, approved_edition=args.edition, reviewer_id=args.reviewer,
            rights_attestation=args.rights_note, applicability_attestation=args.applicability_note,
            edition_verification_note=args.edition_note,
            effective_from=args.effective_from, effective_to=args.effective_to)
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))

if __name__ == "__main__":
    main()
