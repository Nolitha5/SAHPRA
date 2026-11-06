from m2.assessor_checklist import prompts,CHECKS

def test_s4_five_subsections_and_s5():
    assert all(s in CHECKS for s in ('3.2.S.4.1','3.2.S.4.2','3.2.S.4.3','3.2.S.4.4','3.2.S.4.5','3.2.S.5'))

def test_never_regulatory_approval():
    x=prompts('3.2.S.4.3',extracted_sponsor_fields={'validation_evidence':'Synthetic validation table'})
    assert x['regulatory_verdict'] is None
    assert x['decision']=='HUMAN_ASSESSMENT_REQUIRED'
    assert x['checklist'][0]['capture_state']=='REPORTED'
    assert x['checklist'][1]['capture_state']=='NEEDS_REVIEW'

def test_unrecognised_section_no_invented_rule():
    x=prompts('3.2.S.999')
    assert x['checklist']==[] and x['regulatory_verdict'] is None
