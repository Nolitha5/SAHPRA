"""Local v0.9 smoke validation. Never asserts regulatory or expert validation."""
import argparse
import json
import sqlite3
from pathlib import Path
from m2.compendia_ingest import search_unverified
from m2.assessor_checklist import prompts


def validate(db:Path, guidance_index:Path):
    with sqlite3.connect(str(db)) as con:
        counts={'documents':con.execute('SELECT COUNT(*) FROM documents').fetchone()[0],
                'passages':con.execute('SELECT COUNT(*) FROM passages').fetchone()[0],
                'archives':con.execute('SELECT COUNT(*) FROM archive_sources').fetchone()[0],
                'source_families':dict(con.execute('SELECT source_family,COUNT(*) FROM documents GROUP BY source_family').fetchall()),
                'approval_fields_true':con.execute('SELECT COUNT(*) FROM documents WHERE licence_verified != 0 OR applicability_verified != 0').fetchone()[0]}
    terms=['Ibuprofen','Paracetamol','Amoxicillin','Metronidazole']
    searches={t:search_unverified(db,t,limit=3,include_unreviewed=True) for t in terms}
    iprp_rows=sum(1 for _ in guidance_index.open(encoding='utf-8'))
    checklist=prompts('3.2.S.4.3')
    return {'status':'RESEARCH_DISCOVERY_ONLY', 'counts':counts,
            'iprp_indexed_pages':iprp_rows,'test_queries':{k:len(v['hits']) for k,v in searches.items()},
            's4_validation_prompt_count':len(checklist['checklist']),
            'no_promotion_to_regulatory_evidence':counts['approval_fields_true']==0,
            'expert_validated':False,'BGE_Chroma_validated':False,'human_regulatory_approval_performed':False}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--db',type=Path,default=Path('artifacts/quarantine/compendial_discovery.sqlite3'))
    ap.add_argument('--iprp',type=Path,default=Path('artifacts/iprp/IPRP_PAGE_INDEX.jsonl'))
    a=ap.parse_args();print(json.dumps(validate(a.db,a.iprp),indent=2))
