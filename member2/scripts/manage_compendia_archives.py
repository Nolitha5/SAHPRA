"""Member 2 private compendial archive discovery CLI (never promotes to RERA evidence)."""
import argparse
import json
from pathlib import Path
from m2.compendia_ingest import inventory_archives,build_discovery,search_unverified


def main():
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest='command', required=True)
    for cmd in ('inventory','build'):
        q=sub.add_parser(cmd);q.add_argument('--archive-dir',type=Path,default=Path('data/external_archives'))
        if cmd=='build':
            q.add_argument('--db',type=Path,default=Path('artifacts/quarantine/compendial_discovery.sqlite3'))
            q.add_argument('--max-documents',type=int,default=None)
            q.add_argument('--report',type=Path,default=Path('artifacts/quarantine/BUILD_REPORT.json'))
    s=sub.add_parser('search');s.add_argument('--db',type=Path,default=Path('artifacts/quarantine/compendial_discovery.sqlite3'))
    s.add_argument('--query',required=True);s.add_argument('--source-family');s.add_argument('--topic');s.add_argument('--limit',type=int,default=5)
    s.add_argument('--research-only',action='store_true');s.add_argument('--exact-title',action='store_true')
    args=ap.parse_args()
    if args.command=='inventory':result=inventory_archives(args.archive_dir)
    elif args.command=='build':
        result=build_discovery(args.archive_dir,args.db,max_documents=args.max_documents)
        args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(result,indent=2),encoding='utf-8')
    else:result=search_unverified(args.db,args.query,source_family=args.source_family,topic=args.topic,limit=args.limit,exact_title=args.exact_title,include_unreviewed=args.research_only)
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
