"""Reproducible evidence-gap handoff for M1/M4/M5 until official monographs arrive."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from m2.deferred_handoff import build_handoff, dataset_readiness, load_cases
from m2.pharmacopoeia import PharmacopoeiaCatalogue


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default='.')
    ap.add_argument('--cases', default='examples/deferred_s4_s5_synthetic_cases.json')
    ap.add_argument('--catalogue', default='pharmacopoeia/WHO_PHINT_RESEARCH_CATALOGUE_v0.7.json')
    ap.add_argument('--index', default='artifacts/quarantine/compendial_discovery.sqlite3')
    ap.add_argument('--out', default='artifacts/deferred_handoff_v1.0')
    ap.add_argument('--include-research-leads', action='store_true', help='Only quarantine metadata, never cited evidence')
    opt=ap.parse_args()
    root=Path(opt.root).resolve()
    def resolve(v):
        x=Path(v);return x if x.is_absolute() else root/x
    catalogue=PharmacopoeiaCatalogue.load(resolve(opt.catalogue))
    cases=load_cases(resolve(opt.cases))
    index=resolve(opt.index)
    if opt.include_research_leads and not index.exists():
        raise SystemExit(f'Research index not found: {index}')
    records=[build_handoff(c,catalogue,research_index=index if opt.include_research_leads else None,
                           include_unreviewed_candidates=opt.include_research_leads) for c in cases]
    report=dataset_readiness(records)
    target=resolve(opt.out);target.mkdir(parents=True, exist_ok=True)
    for item in records:
        (target/f'{item["case_id"]}.json').write_text(json.dumps(item,indent=2,ensure_ascii=False),encoding='utf-8')
    (target/'TECHNICAL_HANDOFF_REPORT.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
