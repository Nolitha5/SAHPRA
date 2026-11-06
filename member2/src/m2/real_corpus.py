"""Index verified, user-supplied *real* regulatory PDFs for engineering-only RAG preview.

Purpose: actual text corpus, actual persistent vectors, actual source/page anchors.
NOT: expert approval, SAHPRA authorisation, ChromaDB, model fine-tuning, or BGE validation.
The SHA-256 proves local content identity, not identity with the hosted publisher bytes.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter
import fitz
from .chunking import section_chunks
from .embeddings import HashEmbedder
from .sqlite_vectors import SQLiteVectorStore
from .retrieval import lexical_bm25, tokenize

KNOWN = {
    "ICH-M4Q-R1": {"authority":"ICH","code":"M4Q(R1)","version":"R1 (2002-09-12)","filename":"ICH-M4Q-R1.pdf","url":"https://database.ich.org/sites/default/files/M4Q_R1_Guideline.pdf","source_title":"Common Technical Document – Quality", "date":"2002-09-12"},
    "ICH-Q11": {"authority":"ICH","code":"Q11","version":"Step 4 (2012-05-01)","filename":"ICH-Q11.pdf","url":"https://database.ich.org/sites/default/files/Q11_Guideline.pdf","source_title":"Development and Manufacture of Drug Substances", "date":"2012-05-01"},
    "WHO-TRS1010-A10": {"authority":"WHO","code":"TRS 1010 Annex 10","version":"2018","filename":"WHO-TRS1010-Annex10.pdf","url":"https://www.who.int/publications/m/item/trs1010-annex10","source_title":"Stability Testing of APIs and Finished Pharmaceutical Products", "date":"2018-09-30"},
}


def register_additional_from_queue(queue_path:Path):
    """Extend preview indexing to downloaded official-candidate PDFs, without approval."""
    obj=json.loads(Path(queue_path).read_text(encoding='utf-8'))
    for src in obj['sources']:
        KNOWN[src['source_id']]={"authority":src['authority'],"code":src['document_code'],
             "version":src['version_hint'],"filename":src['filename'],"url":src['reference_url'],
             "source_title":src['document_code']+" - " + src['notes'][:50],"date":None,
             "source_group":src.get("selection_group","unclassified"),"priority":src.get("priority","unknown"),
             "review_notes":src.get("notes","")}


def hash_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(1_048_576),b""):h.update(block)
    return h.hexdigest()


def prepare_source(path:Path, sid:str, output:Path, *, size:int=512,overlap:int=128):
    m=KNOWN[sid]
    with fitz.open(path) as pdf:
        if not pdf.page_count:raise ValueError(f"Empty PDF: {path}")
        pages=[(i+1,p.get_text(sort=True)) for i,p in enumerate(pdf)]
        empty=[i for i,text in pages if len(text.strip())<25]
        first=" ".join(x for _,x in pages[:5]).casefold()
    meaningful=sum(len(s.split()) for _,s in pages)
    if meaningful<6:raise ValueError(f"Too little extractable text; OCR required: {path}")
    chunks=section_chunks(sid,pages,size=size,overlap=overlap,default_section=m["code"])
    likely_toc={page for page,text in pages if len(re.findall(r"\.{4,}",text))>=4}
    for ch in chunks:
        ch.metadata.update({"publisher":m["authority"],"publication_version":m["version"],"original_pdf_page":ch.page or 0,
                            "regulatory_approval":"PENDING_EXPERT_REVIEW","source_type":"regulatory_reference",
                            "likely_table_of_contents": ch.page in likely_toc,
                            "source_group":m.get("source_group","core"),
                            "requires_product_scope_review":m.get("source_group")=="conditional_biologics",
                            "source_review_notes":m.get("review_notes","") if sid=="SAHPRA-PEM-02-V9" else ""})
    entry=dict(source_id=sid,authority=m['authority'],document_code=m['code'],title=m['source_title'],version=m['version'],
               issue_date=m['date'],official_reference_url=m['url'],pdf_file=m['filename'],sha256=hash_file(path),
               page_count=len(pages),empty_or_sparse_pages=empty,approximate_words=meaningful,chunk_count=len(chunks),
               origin_check="TITLE_DATE_CONSISTENT_WITH_SUPPLIED_REFERENCE_NOT_BYTE_MATCHED",
               regulatory_approved=False,domain_reviewer=None,applicability_verified=False,
               source_group=m.get("source_group","core"),
               requires_product_scope_review=m.get("source_group")=="conditional_biologics",
               filename_id_verified=True, extracted_content="LOCAL_USER_SUPPLIED_PDF")
    if sid=="ICH-M4Q-R1" and "m4q" not in first:raise ValueError("Uploaded M4Q identifier not found in first pages")
    if sid=="ICH-Q11" and "q11" not in first:raise ValueError("Uploaded Q11 identifier not found in first pages")
    if sid=="WHO-TRS1010-A10" and "annex 10" not in first:raise ValueError("WHO annex identifier not found")
    return entry,chunks


def index_uploaded(inputs:dict[str,Path],output:Path,*,size=512,overlap=128,dimension=384):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    if not inputs:raise ValueError('No PDFs specified')
    embed=HashEmbedder(dimension)
    db=output/'real_reference_preview.sqlite3'
    if db.exists():db.unlink()  # rebuild snapshot deterministically; never merge stale sources
    store=SQLiteVectorStore(embed,db)
    entries=[];all_chunks=[]
    seen_hashes={}
    for sid,path in inputs.items():
        path=Path(path)
        if sid not in KNOWN:raise ValueError('Unknown reference: '+sid)
        if not path.is_file():raise FileNotFoundError(path)
        digest=hash_file(path)
        if digest in seen_hashes:raise ValueError(f'Duplicate source PDF: {sid} duplicates {seen_hashes[digest]}')
        seen_hashes[digest]=sid
        entry,chunks=prepare_source(path,sid,output,size=size,overlap=overlap)
        all_chunks.extend(chunks);entries.append(entry)
    store.upsert(all_chunks)
    assert store.count()==len(all_chunks)
    store.close()
    manifest={"created_at_utc":datetime.now(timezone.utc).isoformat(),"corpus_status":"REAL_USER_SUPPLIED_REFERENCE_PDFS_TECHNICAL_PREVIEW_ONLY",
              "regulatory_applicability_status":"NOT_EXPERT_APPROVED","index_backend":"SQLite persistent vector fallback (NOT ChromaDB)",
              "embedding_model":"hash-demo-v1 (NOT BGE/semantic model)","embedding_dimension":dimension,
              "chunk_method":"section-aware, PDF-page-anchored, whitespace approximation", "chunk_size":size,"chunk_overlap":overlap,
              "index_complete":True,"expert_validated":False,"suitable_for_regulatory_decisions":False,
              "sources":entries,"unique_document_count":len(entries),"indexed_chunk_count":len(all_chunks),
              "warnings":["Source PDFs are user supplied. Publisher URLs identified, but downloaded-byte identity not proven.",
                          "Indexing is not SAHPRA endorsement or scientific regulatory approval.",
                          "Use actual BGE embeddings and ChromaDB on dependency-enabled machine; rebuild index after model change."]}
    (output/'REAL_CORPUS_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    with (output/'REGULATORY_CHUNKS.jsonl').open('w',encoding='utf-8') as f:
        for c in all_chunks:f.write(c.model_dump_json()+'\n')
    with (output/'SOURCE_REGISTER.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(entries[0]));writer.writeheader();writer.writerows(entries)
    return manifest


def preview_query(index_dir:Path,question:str,*,top_k:int=5,code:str|None=None):
    if not question.strip():raise ValueError('question required')
    folder=Path(index_dir);manifest=json.loads((folder/'REAL_CORPUS_MANIFEST.json').read_text(encoding='utf-8'))
    embed=HashEmbedder(int(manifest['embedding_dimension']))
    store=SQLiteVectorStore(embed,folder/'real_reference_preview.sqlite3')
    chunks=[c for c in store.all_chunks() if not c.metadata.get("likely_table_of_contents")]
    if code:chunks=[c for c in chunks if next((s['document_code'] for s in manifest['sources'] if s['source_id']==c.source_id),'').casefold()==code.casefold()]
    if not chunks:return {"status":"NO_PREVIEW_MATCH","evidence":[],"human_review_required":True,"preview_only":True}
    bm25=lexical_bm25(question,chunks)
    dense={c.chunk_id:score for c,score in store.search(question,limit=store.count())}
    dense_rank={cid:i+1 for i,(cid,score) in enumerate(sorted(((c.chunk_id,dense.get(c.chunk_id,0)) for c in chunks),key=lambda item:(-item[1],item[0])))}
    lexical_rank={cid:i+1 for i,(cid,score) in enumerate(sorted(bm25.items(),key=lambda item:(-item[1],item[0])))}
    source_map={s['source_id']:s for s in manifest['sources']}
    matches=[]
    qt=set(tokenize(question))
    for c in chunks:
        s=source_map[c.source_id]
        if not qt.intersection(tokenize(c.text+' '+s['title']+' '+s['document_code'])):continue
        score=0.5/(60+dense_rank[c.chunk_id])+0.5/(60+lexical_rank[c.chunk_id])
        matches.append((score,c,s))
    matches.sort(key=lambda item:(-item[0],item[1].chunk_id))
    result=[]
    for score,c,s in matches[:top_k]:
        result.append({"chunk_id":c.chunk_id,"source_id":c.source_id,"document_code":s['document_code'],
                       "section":c.section,"original_pdf_page":c.page,"citation":f"{s['authority']} {s['document_code']} ({s['version']}), PDF page {c.page}",
                       "publisher_url":s['official_reference_url'],"sha256":s['sha256'],"retrieval_rff_score":round(score,7),
                       "text":c.text,"regulatory_approved":False})
    store.close()
    return {"status":"PREVIEW_MATCH" if result else "NO_PREVIEW_MATCH","query":question,"evidence":result,
            "preview_only":True,"human_review_required":True,"expert_validated":False,
            "warning":"Real document excerpts; offline hash/lexical retrieval. Not Chroma/BGE, expert labels, or regulatory findings."}


def main():
    parser=argparse.ArgumentParser(description='REAL PDFs -> persistent offline engineering preview index')
    sub=parser.add_subparsers(dest='command',required=True)
    idx=sub.add_parser('index')
    idx.add_argument('--m4q',type=Path,required=True);idx.add_argument('--q11',type=Path,required=True)
    idx.add_argument('--who',type=Path,required=True);idx.add_argument('--out',type=Path,default=Path('artifacts/real_corpus'))
    idx.add_argument('--chunk-size',type=int,default=512);idx.add_argument('--overlap',type=int,default=128)
    idx.add_argument('--additional-dir',type=Path,default=None,help='Directory with additional official PDF candidates')
    idx.add_argument('--additional-queue',type=Path,default=Path('regulatory_sources/OFFICIAL_ADDITIONAL_DOWNLOAD_QUEUE.json'))
    sr=sub.add_parser('search');sr.add_argument('--index',type=Path,default=Path('artifacts/real_corpus'))
    sr.add_argument('--query',required=True);sr.add_argument('--code');sr.add_argument('--top-k',type=int,default=5)
    args=parser.parse_args()
    if args.command=='index':
        sources={'ICH-M4Q-R1':args.m4q,'ICH-Q11':args.q11,'WHO-TRS1010-A10':args.who}
        if args.additional_dir:
            register_additional_from_queue(args.additional_queue)
            for sid,entry in KNOWN.items():
                if sid not in sources and (args.additional_dir/entry['filename']).exists():
                    sources[sid]=args.additional_dir/entry['filename']
        report=index_uploaded(sources,args.out,size=args.chunk_size,overlap=args.overlap)
        print(json.dumps({'unique_document_count':report['unique_document_count'],'indexed_chunk_count':report['indexed_chunk_count'],
                         'index_backend':report['index_backend'],'manifest':str(args.out/'REAL_CORPUS_MANIFEST.json')},indent=2))
    else:print(json.dumps(preview_query(args.index,args.query,top_k=args.top_k,code=args.code),indent=2))

if __name__=='__main__':main()
