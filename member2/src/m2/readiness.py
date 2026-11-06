"""Fail-closed release gates. Presence of evidence != authorisation or scientific verification."""
from __future__ import annotations
from pathlib import Path
import importlib.util, json
from .registry import SourceRegistry,file_sha256

REQUIRED_TEAM_ARTIFACTS={
 'm1':'integration_evidence/m1_live_graph_report.json',
 'm3':'integration_evidence/m3_real_dossier_extraction_report.json',
 'm4':'integration_evidence/m4_full_evaluation_report.json',
 'm5':'integration_evidence/m5_domain_qa_and_expert_signoff.json',
}

def readiness(root:str|Path) -> dict:
    root=Path(root)
    checks=[]
    def add(name,good,detail):checks.append({'check':name,'passed':bool(good),'detail':detail})
    has_chroma=importlib.util.find_spec('chromadb') is not None
    has_models=importlib.util.find_spec('sentence_transformers') is not None
    add('chromadb_installed',has_chroma,'Native ChromaDB dependency required for persistence')
    add('embedding_runtime_installed',has_models,'SentenceTransformers and target BGE models required')
    registry=SourceRegistry.load(root/'local_indexes/sources.json')
    approved=[r for r in registry.records.values() if r.approved and r.provenance_verified and r.source_type.value=='regulatory']
    verified=[]
    for r in approved:
        file=root/'regulatory_sources'/f'{r.source_id}.pdf'
        if file.exists() and r.sha256 and file_sha256(file)==r.sha256:verified.append(r.source_id)
    add('approved_official_pdf_corpus',len(verified)>=3,
        f'{len(verified)} verified source PDF(s); minimum 3 for engineering gate, coverage review still required')
    for member,relative in REQUIRED_TEAM_ARTIFACTS.items():
        add(f'{member}_live_component_evidence',(root/relative).is_file(),f'Expected: {relative}')
    labels=root/'regulatory_sources/expert_labels.json'
    add('expert_labels_supplied',labels.is_file(),'Requires M5 domain sign-off; file presence does not attest expertise')
    add('pilot_approval_supplied',(root/'pilot_evidence/pilot_authorisation.json').is_file(),
        'External ethics, data-protection, institutional and assessor approvals required')
    add('human_pilot_records_supplied',(root/'pilot_evidence/assessor_pilot_results.json').is_file(),
        'Authenticated assessor outcomes and approved controlled pilot protocol required')
    all_good=all(x['passed'] for x in checks)
    return {'status':'DOCUMENTARY_EVIDENCE_PRESENT_REQUIRES_HUMAN_AUDIT' if all_good else 'NOT_READY_FOR_AUTHORISED_PILOT',
            'checks':checks,'passed_count':sum(c['passed'] for c in checks),
            'required_count':len(checks),'external_verification_required':True,
            'warning':'No file-presence gate can certify regulatory validity or human approval.'}

if __name__=='__main__':
    import argparse
    a=argparse.ArgumentParser();a.add_argument('--root',default='.');a.add_argument('--out',default='validation/RESEARCH_AND_PILOT_READINESS.json')
    p=a.parse_args();r=readiness(p.root)
    dest=Path(p.out);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps(r,indent=2))
    raise SystemExit(0 if r['status']=='DOCUMENTARY_EVIDENCE_PRESENT_REQUIRES_HUMAN_AUDIT' else 2)
