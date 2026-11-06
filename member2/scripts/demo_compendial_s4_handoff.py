"""Demonstrate guarded candidate-search and nonbinding S.4/S.5 checklist handoff."""
import argparse,json
from pathlib import Path
from m2.compendia_ingest import search_unverified
from m2.assessor_checklist import prompts
p=argparse.ArgumentParser();p.add_argument('--db',type=Path,default=Path('artifacts/quarantine/compendial_discovery.sqlite3'))
p.add_argument('--substance',default='Ibuprofen');p.add_argument('--section',default='3.2.S.4.1')
a=p.parse_args()
print(json.dumps({'candidate_discovery':search_unverified(a.db,a.substance,source_family='PH_EUR_EXTRACT',topic='SUBSTANCE_MONOGRAPH',exact_title=True,include_unreviewed=True,limit=2),
                  's4_or_s5_checklist':prompts(a.section),
                  'regulatory_approval':False,'requires_human_review':True},indent=2))
