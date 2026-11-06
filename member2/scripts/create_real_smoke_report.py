from pathlib import Path
import json
from m2.real_corpus import preview_query
idx=Path('artifacts/real_corpus')
qs=[('M4Q-S4','3.2.S.4.3 validation of analytical procedures','M4Q(R1)'),
    ('Q11-CONTROL','drug substance control strategy manufacturing process critical quality attributes','Q11'),
    ('WHO-API-STABILITY','active pharmaceutical ingredient stress testing stability storage conditions','TRS 1010 Annex 10'),
    ('UNANSWERABLE','nonexistentcryptwordz7384 impossible fact','M4Q(R1)')]
result={'evaluation_type':'UNLABELLED_TECHNICAL_SMOKE_TEST_NOT_RETRIEVAL_ACCURACY',
        'expert_approved':False,'model':'hash-demo-v1','queries':[]}
for qid,query,filter_code in qs:
    r=preview_query(idx,query,code=filter_code,top_k=3)
    result['queries'].append({'query_id':qid,'query':query,'filter_code':filter_code,'status':r['status'],
        'human_review_required':r['human_review_required'],
        'hits':[{'chunk_id':e['chunk_id'],'source_id':e['source_id'],'pdf_page':e['original_pdf_page'],
                 'sha256':e['sha256'],'citation':e['citation'],'text_preview':e['text'][:240]} for e in r['evidence']]})
(idx/'QUERY_SMOKE_RESULTS.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({'query_count':len(qs),'matched':[{'query_id':i['query_id'],'hits':len(i['hits'])} for i in result['queries']]},indent=2))
