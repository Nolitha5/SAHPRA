"""Researcher attestation after manual review of official source PDF and licence."""
import argparse,json
from m2.curation import curate
p=argparse.ArgumentParser()
p.add_argument('--acquisition',required=True)
p.add_argument('--pdf-dir',default='regulatory_sources')
p.add_argument('--registry',default='local_indexes/sources.json')
p.add_argument('--reviewer',required=True)
p.add_argument('--verified-version',required=True)
p.add_argument('--licence-assessment',required=True)
p.add_argument('--applicability-assessment',required=True)
p.add_argument('--effective-from',default=None)
p.add_argument('--cover-discrepancy-resolution',default=None)
a=p.parse_args()
print(json.dumps(curate(a.acquisition,a.pdf_dir,a.registry,reviewer_id=a.reviewer,
    approved_version=a.verified_version,licence_attestation=a.licence_assessment,
    reviewed_regulatory_applicability=a.applicability_assessment,effective_from=a.effective_from,
    cover_discrepancy_resolution=a.cover_discrepancy_resolution),indent=2))
