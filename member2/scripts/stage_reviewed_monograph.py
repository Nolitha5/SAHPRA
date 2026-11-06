"""Verify a future human-reviewed official PDF without automatically approving its content."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from m2.monograph_onboarding import ReviewedSourceProposal, stage_submission


def main():
    a=argparse.ArgumentParser()
    a.add_argument('--proposal', required=True)
    a.add_argument('--pdf', required=True)
    a.add_argument('--out',default='artifacts/monograph_review_staging')
    opt=a.parse_args()
    proposal=ReviewedSourceProposal.model_validate_json(Path(opt.proposal).read_text(encoding='utf-8'))
    print(json.dumps(stage_submission(proposal,Path(opt.pdf),Path(opt.out)),indent=2))

if __name__=='__main__':main()
