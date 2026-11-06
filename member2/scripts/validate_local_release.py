"""One-command reproducibility evidence collection without falsely passing blocked steps."""
from pathlib import Path
import subprocess,sys,json,datetime,platform
from m2.chroma_validation import validate_chroma
from m2.readiness import readiness
from m2.team_simulation import simulate_team
from m2.label_governance import template
from m2.source_acquisition import save_catalogue

root=Path(__file__).resolve().parents[1]
output=root/'validation';output.mkdir(parents=True,exist_ok=True)
command=[sys.executable,'-m','pytest','-q','tests']
test=subprocess.run(command,cwd=root,capture_output=True,text=True,timeout=240)
(output/'PYTEST_FULL_RUN.txt').write_text(test.stdout+'\n'+test.stderr,encoding='utf-8')
chroma=validate_chroma()
(output/'CHROMA_RUNTIME_CHECK.json').write_text(json.dumps(chroma,indent=2),encoding='utf-8')
sim=simulate_team(root,root/'artifacts'/'synthetic_team_simulation')
ready=readiness(root)
(output/'RESEARCH_AND_PILOT_READINESS.json').write_text(json.dumps(ready,indent=2),encoding='utf-8')
save_catalogue(root/'regulatory_sources'/'OFFICIAL_SOURCE_CATALOGUE.json')
report={'recorded_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'python':sys.version,'platform':platform.platform(),
        'unit_tests':{'status':'PASS' if test.returncode==0 else 'FAIL',
                      'return_code':test.returncode,'last_lines':test.stdout.strip().splitlines()[-3:]},
        'native_chromadb':chroma,'synthetic_team_contract_simulation':sim,
        'official_corpus_indexed_and_verified':False if ready['passed_count']==0 else 'CHECK_READINESS_REPORT',
        'expert_evaluation_completed':False,'authorised_regulatory_pilot_completed':False,
        'research_and_pilot_readiness':ready['status'],
        'limitations':'Offline execution cannot acquire official PDFs or install ChromaDB; assessor approvals and partner code not supplied.'}
(output/'ADVANCED_VALIDATION_REPORT.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({'unit_tests':report['unit_tests'],'chroma':chroma['status'],
    'simulated_handoff':sim['execution_type'],'pilot_readiness':ready['status']},indent=2))
raise SystemExit(test.returncode)
