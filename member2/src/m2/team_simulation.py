"""Deterministic *synthetic* five-member contract simulation (NOT a SAHPRA pilot).

Real integration requires M1–M5 source code, reviewer permissions and a human assessor.
No AI or synthetic pass here is evidence of clinical/regulatory validity.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import hashlib,json,sqlite3
from .cli import load_demo
from .runtime import M2Runtime, AppConfig
from .integration import evidence_node, s4_node
from .schemas import EvidenceRequest, EvidenceStatus, Finding, QAStatus, S4ReviewRequest


def _now():return datetime.now(timezone.utc).isoformat()

class SyntheticM4Audit:
    """Local SQLite integration contract simulator, not M4 production implementation."""
    def __init__(self,db:str|Path):
        db=Path(db);db.parent.mkdir(parents=True,exist_ok=True)
        self.conn=sqlite3.connect(db)
        self.conn.execute('create table if not exists audit (id integer primary key, case_id text, event text, payload_json text, timestamp_utc text)')
        self.conn.commit()
    def record(self,case_id,event,payload):
        self.conn.execute('insert into audit(case_id,event,payload_json,timestamp_utc) values (?,?,?,?)',
                          (case_id,event,json.dumps(payload,sort_keys=True),_now()))
        self.conn.commit()
    def history(self,case_id):
        return [{'event':r[0],'payload':json.loads(r[1]),'timestamp_utc':r[2]} for r in
            self.conn.execute('select event,payload_json,timestamp_utc from audit where case_id=? order by id',(case_id,))]
    def close(self):self.conn.close()


def qa_critic_stub(findings:list[Finding]) -> list[Finding]:
    """Simple required-field contract check, NOT a substitute for M5's scientific QA."""
    checked=[]
    for finding in findings:
        # Failure to retrieve a source never becomes a QA pass.
        good=bool(finding.regulatory_evidence) and all(p.citation.strip() and p.passage.strip() for p in finding.regulatory_evidence)
        good=good and bool(finding.sponsor_evidence) and all(p.ctd_section for p in finding.sponsor_evidence)
        finding.qa_status=QAStatus.PASS if good else QAStatus.FLAG
        finding.attributes['qa_method']='SYNTHETIC_REQUIRED_FIELDS_CHECK_NOT_DOMAIN_VALIDATION'
        checked.append(finding)
    return checked


def simulate_team(project_root:str|Path,output_dir:str|Path):
    """Exercises actual M2 with simulated inputs/handoffs for all other members."""
    root=Path(project_root);out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    runtime=M2Runtime(AppConfig.from_file(root/'config/default.json'))
    load_demo(runtime,str(root/'examples'))
    case=json.loads((root/'examples/synthetic_s4_case.json').read_text(encoding='utf-8'))
    case['case_id']='SIMULATED-CASE-001'
    qa_records=[]
    audit=SyntheticM4Audit(out/'synthetic_case_audit.sqlite3')
    audit.record(case['case_id'],'M1_ACCEPT_REQUEST',{'actor':'SYNTHETIC_AUTOMATED_ORCHESTRATOR'})
    audit.record(case['case_id'],'M3_INGESTION_STUB',{
        'source':'examples/synthetic_s4_case.json','is_real_dossier':False,
        'sections':[x['ctd_section'] for x in case['dossier_chunks']]})
    evidence_req=EvidenceRequest(request_id='SIM-REQ-001',question='drug substance analytical validation accuracy precision',
                                 requesting_agent='S1_IDENTITY',case_id=case['case_id'],top_k=3)
    evidence_patch=evidence_node(runtime)({'evidence_request':evidence_req.model_dump(mode='json')})
    audit.record(case['case_id'],'M2_RERA_RETURN',{'status':evidence_patch['evidence_result']['status'],
                         'sources':[p['citation'] for p in evidence_patch['evidence_result']['evidence']]})
    review_patch=s4_node(runtime)({'s4_request':case})
    audit.record(case['case_id'],'M2_S4_FINDINGS',{'count':len(review_patch['findings'])})
    # M4 cross-section and M5 QA are executable contract stubs, not implementations of those agents.
    findings=[Finding.model_validate(x) for x in review_patch['findings']]
    audit.record(case['case_id'],'M4_CONSISTENCY_STUB',{'status':'NOT_IMPLEMENTED_EXTERNAL_M4_REQUIRED'})
    for finding in qa_critic_stub(findings):
        qa_records.append({'finding_id':finding.finding_id,'qa_status':finding.qa_status.value})
        audit.record(case['case_id'],'M5_QA_FIELDS_STUB',{'finding_id':finding.finding_id,
                          'status':finding.qa_status.value,'not_expert_validated':True})
    # Simulated human UI interaction is NEVER an assessor decision or approval.
    audit.record(case['case_id'],'HUMAN_GATE_SIMULATED_ONLY',{
        'ui_member':'M5', 'action':'QUERY', 'actor':'SYNTHETIC_TEST_ACTOR',
        'regulatory_approval':False,'human_assessor_present':False})
    history=audit.history(case['case_id'])
    audit.close()
    assert history[-1]['event']=='HUMAN_GATE_SIMULATED_ONLY'
    report={'study':'SAHPRA Agentic QA-RAG','execution_type':'SYNTHETIC_FIVE_MEMBER_CONTRACT_SIMULATION',
            'not_a_regulatory_pilot':True,'not_expert_evaluated':True,
            'case_id':case['case_id'],'real_members_integrated':['M2_ONLY'],
            'simulated_member_interfaces':['M1','M3','M4','M5'],
            'm2_evidence_status':evidence_patch['evidence_result']['status'],
            'm2_evidence_is_synthetic':all(x['is_synthetic'] for x in evidence_patch['evidence_result']['evidence']),
            'm2_s4_finding_count':len(findings),'qa_stub_results':qa_records,
            'human_decision':'NO_AUTHORISED_HUMAN_DECISION','audit_events':len(history),
            'audit_db':str(out/'synthetic_case_audit.sqlite3'),
            'pending':['M1 actual graph','M3 actual PDF extractor','M4 actual memory/evaluation',
                       'M5 actual QA/domain review','actual regulatory corpus',
                       'ethical/pilot approval and authorised assessors']}
    (out/'synthetic_integration_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (out/'synthetic_audit_events.json').write_text(json.dumps(history,indent=2),encoding='utf-8')
    return report

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--root',default='.');p.add_argument('--out',default='artifacts/synthetic_team_simulation')
    a=p.parse_args(); print(json.dumps(simulate_team(a.root,a.out),indent=2))
